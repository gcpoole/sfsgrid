"""Fetch all session detail pages listed in sfs2026_schedule.json.

Saves each to raw_html/sessions/<id>.html. Skips files already present
(safe to re-run). Polite 1 req/sec rate limit.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SCHEDULE_JSON = HERE / "sfs2026_schedule.json"
SESSIONS_DIR = HERE / "raw_html" / "sessions"
BASE = "https://sfs-2026.m.asnevents.com.au"
UA = "Mozilla/5.0 (sfs2026-scrape)"
RATE_LIMIT_SEC = 1.0


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(SCHEDULE_JSON.read_text())

    sessions = [s for day in data["days"] for block in day["blocks"] for s in block["sessions"]]
    print(f"Found {len(sessions)} sessions to fetch.")

    fetched = skipped = errors = 0
    for i, s in enumerate(sessions, 1):
        out_path = SESSIONS_DIR / f"{s['id']}.html"
        if out_path.exists():
            skipped += 1
            continue

        url = BASE + s["url"]
        try:
            html = fetch(url)
            out_path.write_bytes(html)
            fetched += 1
            print(f"  [{i:3d}/{len(sessions)}] {s['id']} {len(html):>7d} bytes  {s['title'][:60]}")
        except Exception as e:
            errors += 1
            print(f"  [{i:3d}/{len(sessions)}] {s['id']} ERROR: {e}")

        time.sleep(RATE_LIMIT_SEC)

    print(f"\nDone. fetched={fetched} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    main()
