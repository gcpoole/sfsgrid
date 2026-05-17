"""Parse cached session pages and fill in presentations[] in sfs2026_schedule.json.

Two parser branches share one output schema:

  presentation = {
    "time":         "11:00 AM",
    "title":        "Modeling the spread of ...",
    "presenter":    "John M Drake",
    "abstract_id":  "134176"  | None,
    "abstract_url": "https://..." | None,
  }

Standard sessions: parsed from <a class='abstrakt ...'> entries.
Workshop sessions (no abstracts, custom <table>): parsed from the table rows.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
SCHEDULE_JSON = HERE / "sfs2026_schedule.json"
SESSIONS_DIR = HERE / "raw_html" / "sessions"
BASE = "https://sfs-2026.m.asnevents.com.au"

# For workshop rows without a named presenter, synthesize a descriptor.
GROUP_ACTIVITY_LABELS = {
    "workshop activities, including small group breakout sessions": "(breakout activities)",
    "panel-led large group discussion": "(panel discussion)",
}

# Rows that should be skipped entirely (not real time slots).
SKIP_ACTIVITIES = {
    "session and workshop adjourns",
}


def _normalize_time(t: str, block_start: str) -> str:
    """Normalize various time formats to 'H:MM AM/PM'.

    Standard pages already produce '11:00 AM'. Workshop tables produce '10:30'
    or '1:30' with no meridiem — infer from the block start.
    """
    t = t.strip()
    if re.search(r"[AP]M", t, re.I):
        # Already has meridiem; normalize spacing
        return re.sub(r"\s+", " ", t).upper().replace("AM", " AM").replace("PM", " PM").strip()

    # Bare 'H:MM' — infer AM/PM from the block start hour
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if not m:
        return t  # leave it alone if unrecognized
    hour, minute = int(m.group(1)), int(m.group(2))

    # block_start is 'HH:MM' 24h. If the block starts in the morning and this
    # time's hour is < 8, it's PM. Simpler rule: AM if hour >= 8 and <= 11, else PM.
    if 8 <= hour <= 11:
        meridiem = "AM"
    else:
        meridiem = "PM"
    return f"{hour}:{minute:02d} {meridiem}"


def parse_standard(html: str, session_id: str) -> list[dict]:
    """Parse a session page in the standard 'abstrakt' format."""
    soup = BeautifulSoup(html, "html.parser")
    entries = soup.select("a.abstrakt.list-group-item")
    presentations = []
    for a in entries:
        href = a.get("href", "")
        # Extract abstract id from href: /schedule/session/27939/abstract/134176
        m = re.search(r"/abstract/(\d+)$", href)
        abstract_id = m.group(1) if m else None

        title_el = a.select_one("h4.title")
        # Strip the trailing " (134176)" small tag
        if title_el:
            # Remove the <small> that contains the parenthesized id
            for small in title_el.find_all("small"):
                small.decompose()
            title = title_el.get_text(" ", strip=True)
        else:
            title = ""

        time_el = a.select_one(".title-line.time")
        time = time_el.get_text(strip=True) if time_el else ""

        author_el = a.select_one(".title-line.author")
        presenter = author_el.get_text(" ", strip=True) if author_el else ""

        presentations.append({
            "time": time,
            "title": title,
            "presenter": presenter,
            "abstract_id": abstract_id,
            "abstract_url": (BASE + href) if href else None,
        })
    return presentations


def parse_workshop(html: str, block_start: str) -> list[dict]:
    """Parse a workshop session with a custom <table> layout.

    Table columns: Time | Activity | (blank) | Presenters
    Some tables include a header row ('Time'/'Activity'/...); skip it.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Find content table (not in modal/form)
    tables = [
        t for t in soup.find_all("table")
        if not t.find_parent(class_="modal") and not t.find_parent("form")
    ]
    if not tables:
        return []
    table = tables[0]

    presentations = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 4:
            continue
        time_raw, activity, _, presenter_raw = cells[0], cells[1], cells[2], cells[3]

        # Skip header row
        if time_raw.lower() == "time" and activity.lower() == "activity":
            continue

        # Skip end-marker rows
        if activity.strip().lower() in SKIP_ACTIVITIES:
            continue

        # Empty presenter → synthesize from activity
        presenter = presenter_raw.strip()
        if not presenter:
            presenter = GROUP_ACTIVITY_LABELS.get(activity.strip().lower(), "(group activity)")

        time_norm = _normalize_time(time_raw, block_start)

        presentations.append({
            "time": time_norm,
            "title": activity,
            "presenter": presenter,
            "abstract_id": None,
            "abstract_url": None,
        })
    return presentations


def parse_session_file(path: Path, session_id: str, block_start: str) -> list[dict]:
    html = path.read_text(encoding="utf-8")
    standard = parse_standard(html, session_id)
    if standard:
        return standard
    return parse_workshop(html, block_start)


def save_atomic(data: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> None:
    data = json.loads(SCHEDULE_JSON.read_text())

    total_sessions = 0
    total_presentations = 0
    empty_sessions = []

    for day in data["days"]:
        for block in day["blocks"]:
            for session in block["sessions"]:
                total_sessions += 1
                path = SESSIONS_DIR / f"{session['id']}.html"
                if not path.exists():
                    print(f"  MISSING html: {session['id']}")
                    continue
                presentations = parse_session_file(path, session["id"], block["start"])
                session["presentations"] = presentations
                total_presentations += len(presentations)
                if not presentations:
                    empty_sessions.append((session["id"], session["title"]))

    save_atomic(data, SCHEDULE_JSON)

    print(f"Parsed {total_presentations} presentations across {total_sessions} sessions.")
    if empty_sessions:
        print("\nSessions with zero presentations parsed:")
        for sid, title in empty_sessions:
            print(f"  {sid}  {title[:70]}")
    else:
        print("Every session has at least one presentation.")


if __name__ == "__main__":
    main()
