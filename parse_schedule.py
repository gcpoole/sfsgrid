"""Parse SFS 2026 schedule HTML into canonical JSON.

Reads raw_html/full_schedule.html, extracts every chaired session
(presentation session), groups by day -> block -> session, and writes
sfs2026_schedule.json.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
HTML_PATH = HERE / "raw_html" / "full_schedule.html"
OUT_PATH = HERE / "sfs2026_schedule.json"

# Spokane is Pacific. May = PDT = UTC-7.
PACIFIC = timezone(timedelta(hours=-7))

DAY_NAMES = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
    4: "Friday", 5: "Saturday", 6: "Sunday",
}


def parse_dt(raw: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM +0000' (and a malformed variant ending ' 0')."""
    # Some endtime values are '... 0' instead of '... +0000' — normalize.
    raw = raw.strip()
    if raw.endswith(" 0"):
        raw = raw[:-2] + " +0000"
    return datetime.strptime(raw, "%Y-%m-%d %H:%M %z")


def to_pacific(dt: datetime) -> datetime:
    return dt.astimezone(PACIFIC)


def extract_chairs(text: str) -> list[str]:
    """Turn 'Chairs: A & B' or 'Chair: A' into ['A', 'B']."""
    # Strip leading 'Chair:' / 'Chairs:'
    text = re.sub(r"^Chairs?:\s*", "", text.strip())
    # Split on ' & ', ', and ', ', '
    parts = re.split(r"\s*&\s*|\s*,\s*and\s*|\s*,\s*", text)
    return [p.strip() for p in parts if p.strip()]


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    session_anchors = soup.select("a.list-group-item.session")

    # Group: date -> (block_start, block_end) -> [session, ...]
    by_day_block: dict[str, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))

    skipped_no_chairs = 0
    for a in session_anchors:
        chairs_el = a.select_one(".session-chairs .chairman")
        if not chairs_el:
            skipped_no_chairs += 1
            continue

        sid = a.get("data-entity", "").replace("session_", "")
        start_utc = parse_dt(a["data-starttime"])
        end_utc = parse_dt(a["data-endtime"])
        start_local = to_pacific(start_utc)
        end_local = to_pacific(end_utc)

        title_el = a.select_one("h4.title")
        title = title_el.get_text(strip=True) if title_el else ""

        venue_el = a.select_one(".title-line.venue")
        if venue_el:
            # Strip the icon, keep the trailing text
            venue = venue_el.get_text(strip=True)
        else:
            venue = ""

        chairs = extract_chairs(chairs_el.get_text(" ", strip=True))

        session = {
            "id": sid,
            "title": title,
            "room": venue,
            "chairs": chairs,
            "url": a.get("href", ""),
            "start_local": start_local.strftime("%H:%M"),
            "end_local": end_local.strftime("%H:%M"),
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "presentations": [],
        }

        date_key = start_local.strftime("%Y-%m-%d")
        block_key = (session["start_local"], session["end_local"])
        by_day_block[date_key][block_key].append(session)

    # Build final ordered structure
    days = []
    for date_key in sorted(by_day_block):
        d = datetime.strptime(date_key, "%Y-%m-%d")
        blocks = []
        for (start, end) in sorted(by_day_block[date_key]):
            sessions = sorted(by_day_block[date_key][(start, end)], key=lambda s: s["room"])
            blocks.append({"start": start, "end": end, "sessions": sessions})
        days.append({
            "date": date_key,
            "day_name": DAY_NAMES[d.weekday()],
            "blocks": blocks,
        })

    out = {
        "event": "SFS 2026",
        "location": "Spokane, WA",
        "source_html": str(HTML_PATH.relative_to(HERE)),
        "days": days,
    }

    print(f"Parsed {sum(len(b['sessions']) for d in days for b in d['blocks'])} chaired sessions "
          f"across {len(days)} days (skipped {skipped_no_chairs} non-chaired items).")
    return out


def save_atomic(data: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    data = parse_html(html)
    save_atomic(data, OUT_PATH)
    print(f"Wrote {OUT_PATH}")

    # Quick summary per day
    for day in data["days"]:
        n = sum(len(b["sessions"]) for b in day["blocks"])
        block_summary = ", ".join(
            f"{b['start']}-{b['end']}({len(b['sessions'])})" for b in day["blocks"]
        )
        print(f"  {day['date']} {day['day_name']:9s} {n:3d} sessions  [{block_summary}]")


if __name__ == "__main__":
    main()
