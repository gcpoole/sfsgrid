"""Parse the SFS 2026 talks and posters abstract PDFs into minimal JSON files
suitable for sending to an LLM for similarity analysis.

Output: abstracts/talks.json and abstracts/posters.json, each containing
a list of records: {id, abstract}.

Title, authors, and affiliations are deliberately excluded:
  - Authors/affiliations: similarity should be about content, not authorship
  - Title: nearly always redundant with the abstract's opening, and parsing
    titles reliably is hard because they wrap across lines and sometimes
    look like author rosters (chemical formulas trip the heuristics).
    Titles still live in sfs2026_schedule.json for display.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
ABSTRACTS_DIR = HERE / "abstracts"

# Talks PDF: each entry starts with "id #NNNNNN" header.
TALKS_ID_RE = re.compile(r"^\s*id\s+#(\d+)\s*$")
# Posters PDF: each entry starts with a bare integer (the poster number).
POSTERS_ID_RE = re.compile(r"^\s*(\d{1,4})\s*$")

# Affiliation lines look like "1. University of X, City, ..."
AFFILIATION_RE = re.compile(r"^\d+\.\s+")
# Affiliation continuations sometimes wrap (e.g., "...United\nStates") — short
# non-affiliation lines following an affiliation line are treated as wraps.
AFFIL_CONTINUATION_MAX_CHARS = 100


def ensure_text(pdf_path: Path) -> Path:
    """Run pdftotext -layout if the .txt doesn't already exist."""
    txt_path = pdf_path.with_suffix(".txt")
    if not txt_path.exists():
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
            check=True,
        )
    return txt_path


def is_id_header(line: str, kind: str) -> str | None:
    if kind == "talks":
        m = TALKS_ID_RE.match(line)
    else:
        m = POSTERS_ID_RE.match(line)
    return m.group(1) if m else None


def split_records(lines: list[str], kind: str) -> list[tuple[str, list[str]]]:
    """Yield (id, body_lines) tuples, splitting on id headers."""
    records: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    current_body: list[str] = []
    for line in lines:
        new_id = is_id_header(line, kind)
        if new_id is not None:
            if current_id is not None:
                records.append((current_id, current_body))
            current_id = new_id
            current_body = []
        elif current_id is not None:
            current_body.append(line)
    if current_id is not None:
        records.append((current_id, current_body))
    return records


def parse_record(record_id: str, body_lines: list[str]) -> dict:
    """Extract just the abstract text from a record's body.

    Record layout (after stripping the id header):
        title (1+ lines)
        author roster (1+ lines)
        affiliation lines ("1. ...", "2. ...", with occasional wraps)
        abstract paragraphs (separated by blank lines)
        [optional] numbered references list, after a blank line

    We don't extract the title or authors at all — title is in our schedule
    JSON already, and we explicitly want similarity based on content rather
    than authorship.

    Strategy:
        1. Find the first affiliation line.
        2. Walk past the affiliation block (affil lines + short wraps).
        3. Read the abstract, allowing internal blank-line paragraph breaks.
           Stop at a blank line whose next non-blank starts with "N. "
           (= references section).
    """
    body = [ln.rstrip() for ln in body_lines]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    first_affil_idx = next(
        (i for i, ln in enumerate(body) if AFFILIATION_RE.match(ln.lstrip())),
        -1,
    )
    if first_affil_idx < 0:
        # No affiliations found — fall back to using the whole body.
        abstract = " ".join(ln.strip() for ln in body if ln.strip()).strip()
        return {"id": record_id, "abstract": abstract}

    # Walk past affiliation block: affil lines, short wrap lines, stray blanks.
    i = first_affil_idx
    while i < len(body):
        line = body[i]
        stripped = line.strip()
        if not stripped:
            i += 1
        elif AFFILIATION_RE.match(line.lstrip()):
            i += 1
        elif len(line) < AFFIL_CONTINUATION_MAX_CHARS:
            i += 1  # wrap of preceding affiliation
        else:
            break  # long paragraph line → abstract starts here

    # Walk the abstract, stopping at references (blank line followed by "N. ").
    abstract_lines: list[str] = []
    while i < len(body):
        if body[i].strip():
            abstract_lines.append(body[i])
            i += 1
            continue
        # Blank line — peek at next non-blank.
        j = i + 1
        while j < len(body) and not body[j].strip():
            j += 1
        if j >= len(body):
            break
        if AFFILIATION_RE.match(body[j].lstrip()):
            break  # references section
        i = j  # inter-paragraph break — skip blanks, keep reading

    abstract = " ".join(ln.strip() for ln in abstract_lines if ln.strip()).strip()
    return {"id": record_id, "abstract": abstract}


def parse_pdf(pdf_path: Path, kind: str) -> list[dict]:
    txt_path = ensure_text(pdf_path)
    lines = txt_path.read_text(encoding="utf-8").splitlines()
    raw_records = split_records(lines, kind)
    parsed = [parse_record(rid, body) for rid, body in raw_records]
    return parsed


def save_atomic(data, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def schedule_abstract_ids() -> set[str]:
    """Return the set of abstract IDs that actually appear in our schedule."""
    schedule = json.loads((HERE / "sfs2026_schedule.json").read_text())
    ids = set()
    for day in schedule["days"]:
        for block in day["blocks"]:
            for s in block["sessions"]:
                for p in s["presentations"]:
                    if p.get("abstract_id"):
                        ids.add(p["abstract_id"])
    return ids


def main() -> None:
    talks_all = parse_pdf(ABSTRACTS_DIR / "2026Talks.pdf", "talks")
    posters = parse_pdf(ABSTRACTS_DIR / "2026Posters.pdf", "posters")

    # Filter talks to only those present in our schedule. Abstracts that
    # exist in the PDF but not on the schedule (e.g., withdrawn talks,
    # plenary speakers) are excluded so we don't recommend talks no one
    # can attend.
    sched_ids = schedule_abstract_ids()
    talks = [r for r in talks_all if r["id"] in sched_ids]
    dropped = len(talks_all) - len(talks)

    save_atomic(talks, ABSTRACTS_DIR / "talks.json")
    save_atomic(posters, ABSTRACTS_DIR / "posters.json")

    print(f"talks:   {len(talks)} records → abstracts/talks.json "
          f"(dropped {dropped} not on the schedule)")
    print(f"posters: {len(posters)} records → abstracts/posters.json")

    # Quick sanity: any records with empty abstract?
    for label, records in [("talks", talks), ("posters", posters)]:
        empty_abstract = [r for r in records if not r["abstract"]]
        if empty_abstract:
            print(f"  {label}: {len(empty_abstract)} records with empty abstract")
            for r in empty_abstract[:3]:
                print(f"    id={r['id']}")


if __name__ == "__main__":
    main()
