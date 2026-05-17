"""Survey cached session pages to find structural variations.

Categorizes each by:
  - count of <a class='abstrakt list-group-item'> entries (standard presentations)
  - presence of a custom <table> inside the session description (workshop format)
  - any other pattern that doesn't fit either

Prints a summary so we can decide how to parse each format.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
SESSIONS_DIR = HERE / "raw_html" / "sessions"
SCHEDULE_JSON = HERE / "sfs2026_schedule.json"


def categorize(html: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    abstrakts = soup.select("a.abstrakt.list-group-item")
    abstract_list = soup.select_one("#abstract-list")

    # Custom embedded table inside the session description area
    # (outside the abstract list, outside header/nav/login modal)
    desc_tables = []
    if abstract_list:
        # Tables that appear before #abstract-list or inside the description body
        pass
    all_tables = soup.find_all("table")
    # Filter out tables that are clearly UI chrome (login forms, etc.)
    content_tables = [
        t for t in all_tables
        if not t.find_parent(class_="modal")
        and not t.find_parent("form")
    ]

    info = {
        "abstrakt_count": len(abstrakts),
        "has_abstract_list_div": abstract_list is not None,
        "content_table_count": len(content_tables),
        "abstract_list_empty": abstract_list is not None and len(abstrakts) == 0,
    }

    if abstrakts:
        category = "standard"
    elif content_tables:
        category = "custom_table"
    elif abstract_list is not None and len(abstrakts) == 0:
        category = "empty_abstract_list"
    else:
        category = "unknown"

    return category, info


def main() -> None:
    data = json.loads(SCHEDULE_JSON.read_text())
    session_meta = {}
    for day in data["days"]:
        for block in day["blocks"]:
            for s in block["sessions"]:
                session_meta[s["id"]] = (day["date"], s["title"], s["room"])

    categories = defaultdict(list)
    abstrakt_counts = Counter()

    files = sorted(SESSIONS_DIR.glob("*.html"))
    for f in files:
        sid = f.stem
        cat, info = categorize(f.read_text(encoding="utf-8"))
        categories[cat].append((sid, info))
        abstrakt_counts[info["abstrakt_count"]] += 1

    print(f"=== Summary across {len(files)} sessions ===\n")
    for cat, items in categories.items():
        print(f"{cat}: {len(items)}")

    print("\n=== Talks-per-session distribution (standard format) ===")
    for n in sorted(abstrakt_counts):
        print(f"  {n} talks: {abstrakt_counts[n]} sessions")

    print("\n=== Non-standard sessions (need custom handling) ===")
    for cat in ["custom_table", "empty_abstract_list", "unknown"]:
        if not categories[cat]:
            continue
        print(f"\n-- {cat} --")
        for sid, info in categories[cat]:
            date, title, room = session_meta.get(sid, ("?", "?", "?"))
            print(f"  {sid}  {date}  {room}  {title[:70]}")
            print(f"           {info}")


if __name__ == "__main__":
    main()
