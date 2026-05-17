"""Generate index.html — a time-proportional grid view of SFS 2026.

One self-contained HTML file. Inline CSS. No JS.

Layout:
  - Sticky tab bar (day-grouped jump links)
  - One grid per block, stacked vertically
  - Each grid preceded by a colored title bar (color per day)
  - Vertical axis: time at 8 px/min (4-min lightning ~= one line)
  - Horizontal: one column per session
  - Cells: single line - time | bold presenter | title (truncated, hover for full)
  - Lightning talks (<10 min): just "Lightning Talk"
  - Workshop multi-presenter rows: "(multiple presenters)"
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
SCHEDULE_JSON = HERE / "sfs2026_schedule.json"
OUT_HTML = HERE / "docs" / "index.html"

PX_PER_MIN = 8

# Per-day color palette (muted, professional).
# 'cell' / 'cell_border' / 'cell_hover' are pale tints of 'bar' for talk cells.
DAY_COLORS = {
    "Monday":    {"bar": "#2c7fb8", "fg": "#ffffff",
                  "cell": "#e6f0f8", "cell_border": "#b6cee0", "cell_hover": "#d0e3f0"},
    "Tuesday":   {"bar": "#7a9c3d", "fg": "#ffffff",
                  "cell": "#eef3e0", "cell_border": "#c8d5a4", "cell_hover": "#dfe9c8"},
    "Wednesday": {"bar": "#b8860b", "fg": "#ffffff",
                  "cell": "#f7eed2", "cell_border": "#dfc788", "cell_hover": "#efe1b3"},
    "Thursday":  {"bar": "#a04a7a", "fg": "#ffffff",
                  "cell": "#f1e0ea", "cell_border": "#d4b1c4", "cell_hover": "#e7cddb"},
}

def parse_12h(t: str) -> datetime:
    return datetime.strptime(t.strip(), "%I:%M %p")


def parse_24h(t: str) -> datetime:
    return datetime.strptime(t.strip(), "%H:%M")


def clean_presenter(raw: str) -> str:
    """Strip noise from workshop presenter strings."""
    s = re.sub(r"^\(confirmed\)\s*", "", raw).strip()
    return s


def block_anchor(date: str, start: str) -> str:
    # date = '2026-05-18', start = '11:00' → 'd2026-05-18-1100'
    return "d" + date + "-" + start.replace(":", "")


def day_anchor(date: str) -> str:
    return "day-" + date


def fmt_block_label(start_24h: str) -> str:
    """'11:00' → '11:00 AM', '14:00' → '2:00 PM' — for tab buttons."""
    dt = parse_24h(start_24h)
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_block_range(start_24h: str, end_24h: str) -> str:
    s = parse_24h(start_24h).strftime("%I:%M %p").lstrip("0")
    e = parse_24h(end_24h).strftime("%I:%M %p").lstrip("0")
    return f"{s} – {e}"


def fmt_date_long(date: str) -> str:
    """'2026-05-18' → 'Monday, May 18'."""
    dt = datetime.strptime(date, "%Y-%m-%d")
    return dt.strftime("%A, %B %-d")


def render_cell(presentation: dict, block_start_24h: str, day_color: dict, accordion_name: str) -> str:
    start_dt = parse_12h(presentation["time"])
    block_start_dt = parse_24h(block_start_24h)
    offset_min = int((start_dt - block_start_dt).total_seconds() // 60)
    duration_min = presentation["duration_min"]

    top_px = offset_min * PX_PER_MIN
    height_px = max(duration_min * PX_PER_MIN, PX_PER_MIN * 2)  # min 2px

    presenter_raw = clean_presenter(presentation["presenter"])
    title = presentation["title"]
    time_label = presentation["time"]
    abstract_url = presentation.get("abstract_url")

    # ---- Summary content ----
    # Every cell renders the same: time + full presenter + full title. CSS truncates
    # what doesn't fit when collapsed; expanding the cell un-clips it.
    time_row = f"<div class='cell-time-row'>{escape(time_label)}</div>"
    body_row = (
        f"<div class='cell-body-row'>"
        f"<span class='cell-presenter'>{escape(presenter_raw)}</span>"
        f"<span class='cell-sep'>|</span>"
        f"<span class='cell-title'>{escape(title)}</span>"
        f"</div>"
    )
    summary_inner = f"<div class='cell-inner'>{time_row}{body_row}</div>"

    # ---- Expanded content: just the abstract button. Presenter + title are
    # already in the summary; expanding makes the cell tall enough that the
    # summary's truncated text wraps and shows in full.
    link_html = (
        f"<a class='detail-link' href='{escape(abstract_url)}'>View abstract →</a>"
        if abstract_url else
        "<span class='detail-link detail-link-none'>(no online abstract)</span>"
    )
    detail_html = f"<div class='cell-detail'>{link_html}</div>"

    # collapsed-height is set inline; CSS unsets it when [open] so the cell
    # grows to fit its content.
    style = (
        f"top:{top_px}px;"
        f"--collapsed-height:{height_px}px;"
        f"background:{day_color['cell']};"
        f"border-color:{day_color['cell_border']};"
    )

    return (
        f"<details class='cell' name='{escape(accordion_name)}' style='{style}'>"
        f"<summary class='cell-summary'>{summary_inner}</summary>"
        f"{detail_html}"
        f"</details>"
    )


def render_col_header(session: dict) -> str:
    chairs = ", ".join(session["chairs"])
    chair_label = "Chairs" if len(session["chairs"]) > 1 else "Chair"
    chairs_text = f"{chair_label}: {chairs}"
    header_tooltip = f"{session['title']}\n{chairs_text}"
    return (
        f"<div class='col-header'>"
        f"<div class='col-room'>{escape(session['room'])}</div>"
        f"<div class='col-title' title='{escape(header_tooltip)}'>{escape(session['title'])}</div>"
        f"</div>"
    )


def render_col_body(session: dict, block_start_24h: str, block_height_px: int,
                    day_color: dict, accordion_name: str) -> str:
    cells = "".join(
        render_cell(p, block_start_24h, day_color, accordion_name)
        for p in session["presentations"]
    )
    return f"<div class='col-body' style='height:{block_height_px}px;'>{cells}</div>"


def merge_blocks_per_day(day: dict) -> list[dict]:
    """Merge same-day blocks whose time ranges overlap or are adjacent into one.

    Returns a list of merged 'super-blocks', each with:
      - start, end (earliest start / latest end among merged source blocks)
      - sessions: union of all sessions, each tagged with its own start/end
    """
    src = sorted(day["blocks"], key=lambda b: parse_24h(b["start"]))
    merged: list[dict] = []
    for b in src:
        b_start = parse_24h(b["start"])
        b_end = parse_24h(b["end"])
        if merged and parse_24h(merged[-1]["end"]) >= b_start:
            # Overlap or adjacency → fold in
            cur = merged[-1]
            cur["sessions"].extend(b["sessions"])
            if b_end > parse_24h(cur["end"]):
                cur["end"] = b["end"]
        else:
            merged.append({
                "start": b["start"],
                "end": b["end"],
                "sessions": list(b["sessions"]),
            })
    return merged


def render_block(day: dict, block: dict) -> str:
    color = DAY_COLORS.get(day["day_name"], DAY_COLORS["Monday"])
    anchor = block_anchor(day["date"], block["start"])
    block_start_dt = parse_24h(block["start"])
    block_end_dt = parse_24h(block["end"])
    block_height_px = int((block_end_dt - block_start_dt).total_seconds() // 60) * PX_PER_MIN

    bar = (
        f"<div class='block-bar' id='{anchor}' "
        f"style='background:{color['bar']}; color:{color['fg']};'>"
        f"<span class='block-day'>{escape(fmt_date_long(day['date']))}</span>"
        f"<span class='block-time'>{escape(fmt_block_range(block['start'], block['end']))}</span>"
        f"</div>"
    )

    accordion_name = f"acc-{anchor}"

    header_cells = "".join(
        f"<div class='col'>{render_col_header(s)}</div>"
        for s in block["sessions"]
    )
    body_cells = "".join(
        f"<div class='col'>{render_col_body(s, block['start'], block_height_px, color, accordion_name)}</div>"
        for s in block["sessions"]
    )

    # block-cap (bar + header row) lives OUTSIDE the horizontal-scrolling
    # body-wrap, so vertical sticky pins it against the viewport (same trick
    # the tab bar uses). A tiny JS shim syncs header-row.scrollLeft to
    # body-row.scrollLeft on horizontal scroll only.
    #
    # The body-row is the horizontal scroll container; the inner flex
    # container is a separate element so cells can vertically overflow
    # without being clipped (overflow-x:auto would otherwise clip overflow-y).
    return (
        f"<section class='block'>"
        f"<div class='block-cap'>"
        f"{bar}"
        f"<div class='header-wrap'>"
        f"<div class='header-row'>{header_cells}</div>"
        f"</div>"
        f"</div>"
        f"<div class='body-wrap'>"
        f"<div class='body-scroll'>"
        f"<div class='body-row'>{body_cells}</div>"
        f"</div>"
        f"</div>"
        f"</section>"
    )


def render_tabs(data: dict) -> str:
    """One link per day, side-by-side, mobile-friendly."""
    tabs = []
    for day in data["days"]:
        color = DAY_COLORS.get(day["day_name"], DAY_COLORS["Monday"])
        anchor = day_anchor(day["date"])
        tabs.append(
            f"<a class='tab' href='#{anchor}' "
            f"style='background:{color['bar']}; color:{color['fg']};'>"
            f"{escape(day['day_name'])}</a>"
        )
    return f"<nav class='tab-bar'>{''.join(tabs)}</nav>"


CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  margin: 0; padding: 0;
  background: #f5f5f5; color: #222;
  font-size: 13px; line-height: 1.3;
}
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}
header.page-header {
  background: #222; color: #fff; padding: 12px 16px;
}
header.page-header h1 { margin: 0; font-size: 18px; font-weight: 600; }
header.page-header .subtitle { font-size: 12px; opacity: 0.8; margin-top: 2px; }
.tab-bar {
  position: sticky; top: 0; z-index: 10;
  background: #ffffff; border-bottom: 1px solid #ddd;
  padding: 8px 12px;
  display: flex; gap: 8px; flex-wrap: nowrap;
}
.tab {
  display: inline-block; padding: 6px 14px; border-radius: 4px;
  text-decoration: none; font-size: 13px; font-weight: 600;
  flex: 1 1 0; text-align: center;
  max-width: 160px;
}
.tab:hover { opacity: 0.85; }

section.block { margin: 24px 0; position: relative; }
/* When a cell is open inside this block, raise the entire section's
   stacking context so the open cell can draw over the next block below. */
section.block:has(.cell[open]) { z-index: 100; }

/* The block cap (bar + header row) lives OUTSIDE any horizontal scroll
   container — same as the tab bar — so vertical sticky pins it cleanly to
   the viewport. The body-wrap below it scrolls horizontally. */
.block-cap {
  position: sticky;
  top: 46px;  /* under the day tabs */
  z-index: 5;
  background: #fff;
  margin: 0 12px;
  border: 1px solid #ddd;
  border-bottom: none;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.block-bar {
  padding: 10px 16px; font-weight: 600;
  display: flex; align-items: baseline; gap: 14px;
}
.block-day { font-size: 15px; }
.block-time { font-size: 13px; opacity: 0.9; }

/* Header row scrolls horizontally invisibly — JS syncs it to the body scroll. */
.header-wrap {
  overflow: hidden;
  border-top: 1px solid #ddd;
}
.body-wrap {
  margin: 0 12px;
  border: 1px solid #ddd;
  border-top: none;
  background: #fff;
  /* overflow stays visible so an open cell can escape vertically into the
     space below the block. */
}
.header-row {
  display: flex;
}
/* body-scroll holds the horizontal scroll; overflow-y stays visible so an
   open cell can poke down out of the block. */
.body-scroll {
  overflow-x: auto;
  overflow-y: visible;
}
.body-row {
  display: flex;
}
.col {
  flex: 1 1 0;
  min-width: 160px;
  border-right: 1px solid #eee;
  display: flex; flex-direction: column;
}
.col:last-child { border-right: none; }
.col-header {
  background: #fafafa;
  padding: 6px 8px;
  border-bottom: 1px solid #ccc;
  font-size: 11px;
  height: 80px;
  display: flex; flex-direction: column;
}
.col-room {
  font-weight: 700; color: #444;
  flex: 0 0 auto;
}
.col-title {
  font-weight: 600; margin-top: 2px; color: #222;
  flex: 1 1 auto; overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  line-clamp: 3;
}
.col-body { position: relative; }
.cell {
  position: absolute; left: 2px; right: 2px;
  height: var(--collapsed-height);  /* time-proportional when collapsed */
  border: 1px solid;  /* color set inline per day */
  border-radius: 3px;
  overflow: hidden;
  text-decoration: none; color: inherit;
  display: block;
  transition: filter 0.1s ease;
}
.cell[open] {
  height: auto;  /* let content determine height when expanded */
  min-height: var(--collapsed-height);  /* never shrink below original slot */
  z-index: 30;  /* on top of sticky cap and tabs while open; JS closes on scroll */
  box-shadow: 0 6px 18px rgba(0,0,0,0.28);
  border-color: #555 !important;
  border-width: 2px;
  overflow: visible;
}
.cell-summary {
  list-style: none;
  cursor: pointer;
  overflow: hidden;
}
.cell:not([open]) .cell-summary { height: 100%; }
.cell-summary::-webkit-details-marker { display: none; }
.cell:hover { filter: brightness(0.95); }
.cell-detail {
  padding: 6px 8px 10px;
  border-top: 1px solid rgba(0,0,0,0.15);
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.4;
}
.detail-presenter { font-weight: 700; margin-bottom: 3px; }
.detail-title { color: #222; margin-bottom: 8px; word-break: break-word; }
.detail-link {
  display: inline-block;
  padding: 5px 10px; border-radius: 3px;
  background: #2c7fb8; color: #fff;
  text-decoration: none; font-weight: 600; font-size: 12px;
}
.detail-link:hover { filter: brightness(1.1); }
.detail-link-none {
  background: #ddd; color: #555; cursor: default;
}
.cell-inner {
  padding: 3px 6px;
  overflow: hidden;
  height: 100%;
  word-break: break-word;
}
.cell-time-row {
  color: #666; font-size: 10px;
  margin-bottom: 1px;
}
.cell-body-row {
  overflow: hidden;
}
/* When the cell is expanded, let its content fully show — no clipping. */
.cell[open] .cell-inner,
.cell[open] .cell-body-row {
  overflow: visible;
  height: auto;
}
.cell-sep { color: #aaa; margin: 0 4px; }
.cell-presenter { font-weight: 700; }
.cell-title { color: #333; }
"""


SCROLL_SYNC_JS = """
// (1) Sync each block's header row horizontal scroll to its body row's scroll.
// Vertical sticky on the block-cap is pure CSS — this handler only fires
// during horizontal drag.
// (2) Close any open cell when the page scrolls vertically more than a small
// jitter threshold. Opening a cell floats it above the sticky cap; scrolling
// is a clear "I'm done looking at this" signal.
(function () {
  document.querySelectorAll('section.block').forEach(function (block) {
    var body = block.querySelector('.body-scroll');
    var header = block.querySelector('.header-wrap');
    if (!body || !header) return;
    body.addEventListener('scroll', function () {
      header.scrollLeft = body.scrollLeft;
    }, { passive: true });
  });

  // Close-on-scroll: track the Y position when a cell opens; if the user
  // moves more than 20px from that point, close it.
  var openCell = null;
  var openAtY = 0;

  document.addEventListener('toggle', function (e) {
    if (e.target.matches('details.cell') && e.target.open) {
      openCell = e.target;
      openAtY = window.scrollY;
    } else if (e.target === openCell && !e.target.open) {
      openCell = null;
    }
  }, true);

  window.addEventListener('scroll', function () {
    if (openCell && Math.abs(window.scrollY - openAtY) > 20) {
      openCell.open = false;
      openCell = null;
    }
  }, { passive: true });
})();
"""


def render_page(data: dict) -> str:
    tabs = render_tabs(data)

    # Build merged blocks per day; anchor the *first* block of each day for tab jump.
    parts = []
    for day in data["days"]:
        merged = merge_blocks_per_day(day)
        for i, block in enumerate(merged):
            section_html = render_block(day, block)
            if i == 0:
                # Inject day-level anchor on the first block's section
                day_id = day_anchor(day["date"])
                section_html = section_html.replace(
                    "<section class='block'>",
                    f"<section class='block' id='{day_id}'>",
                    1,
                )
            parts.append(section_html)
    blocks_html = "".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SFS 2026 — Concurrent Session Grid</title>
<style>{CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>SFS 2026 — Concurrent Session Grid</h1>
  <div class="subtitle">Society for Freshwater Science annual meeting · Spokane, WA · May 17–21, 2026 · Click any talk to open its abstract on the official site</div>
</header>
{tabs}
<main>
{blocks_html}
</main>
<script>{SCROLL_SYNC_JS}</script>
</body>
</html>"""


def main() -> None:
    data = json.loads(SCHEDULE_JSON.read_text())
    html = render_page(data)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_HTML.with_suffix(".html.tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, OUT_HTML)
    print(f"Wrote {OUT_HTML} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
