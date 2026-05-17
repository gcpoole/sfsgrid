"""Add end_time and duration_min to every presentation in sfs2026_schedule.json.

Rules:
  - Talk N ends when talk N+1 starts.
  - Last talk in a session ends at session.end_local.

Also prints a duration distribution and flags anomalies so we can sanity-check
the lightning-talk threshold.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SCHEDULE_JSON = HERE / "sfs2026_schedule.json"


def parse_12h(t: str) -> datetime:
    """Parse 'H:MM AM/PM' to a datetime (date is arbitrary, only time matters)."""
    return datetime.strptime(t.strip(), "%I:%M %p")


def parse_24h(t: str) -> datetime:
    """Parse 'HH:MM' (block end_local) to datetime."""
    return datetime.strptime(t.strip(), "%H:%M")


def fmt_12h(dt: datetime) -> str:
    """Format datetime as 'H:MM AM/PM' (no leading zero on hour)."""
    s = dt.strftime("%I:%M %p")
    return s.lstrip("0")  # '11:00 AM' stays, '01:30 PM' -> '1:30 PM'


def save_atomic(data: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> None:
    data = json.loads(SCHEDULE_JSON.read_text())

    duration_counts = Counter()
    anomalies = []

    for day in data["days"]:
        for block in day["blocks"]:
            for session in block["sessions"]:
                pres = session["presentations"]
                if not pres:
                    continue

                session_end = parse_24h(session["end_local"])

                for i, p in enumerate(pres):
                    start = parse_12h(p["time"])
                    if i + 1 < len(pres):
                        end = parse_12h(pres[i + 1]["time"])
                    else:
                        end = session_end

                    duration = int((end - start).total_seconds() // 60)

                    if duration <= 0:
                        anomalies.append((
                            "non-positive duration", session["id"], p["time"],
                            p["title"][:50], duration
                        ))
                    if end > session_end + timedelta(minutes=1):
                        anomalies.append((
                            "ends after session", session["id"], p["time"],
                            p["title"][:50], duration
                        ))

                    p["end_time"] = fmt_12h(end)
                    p["duration_min"] = duration
                    duration_counts[duration] += 1

    save_atomic(data, SCHEDULE_JSON)

    print(f"Updated {sum(duration_counts.values())} presentations with end_time + duration_min.\n")
    print("Duration distribution (min : count):")
    for d in sorted(duration_counts):
        bar = "#" * min(60, duration_counts[d])
        print(f"  {d:>3d} min : {duration_counts[d]:>3d}  {bar}")

    if anomalies:
        print(f"\nAnomalies ({len(anomalies)}):")
        for kind, sid, t, title, dur in anomalies:
            print(f"  [{kind}] session {sid} @ {t} ({dur} min) — {title}")
    else:
        print("\nNo anomalies.")


if __name__ == "__main__":
    main()
