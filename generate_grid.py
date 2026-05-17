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


def render_col_header(session: dict, header_accordion_name: str) -> str:
    chairs = ", ".join(session["chairs"])
    chair_label = "Chairs" if len(session["chairs"]) > 1 else "Chair"
    chairs_suffix = f" · {chair_label}: {chairs}"
    title_with_chairs = f"{session['title']}{chairs_suffix}"
    session_url = "https://sfs-2026.m.asnevents.com.au" + session.get("url", "")
    return (
        f"<details class='col-header' name='{escape(header_accordion_name)}'>"
        f"<summary class='col-header-summary'>"
        f"<div class='col-room'>{escape(session['room'])}</div>"
        f"<div class='col-title' title='{escape(title_with_chairs)}'>"
        f"{escape(session['title'])}"
        f"<span class='col-chairs-suffix'>{escape(chairs_suffix)}</span>"
        f"</div>"
        f"</summary>"
        f"<div class='col-header-detail'>"
        f"<a class='detail-link' href='{escape(session_url)}'>View session →</a>"
        f"</div>"
        f"</details>"
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
      - sessions: union of all sessions, sorted by room so same-room sessions
        end up in adjacent columns
    """
    src = sorted(day["blocks"], key=lambda b: parse_24h(b["start"]))
    merged: list[dict] = []
    for b in src:
        b_start = parse_24h(b["start"])
        b_end = parse_24h(b["end"])
        if merged and parse_24h(merged[-1]["end"]) >= b_start:
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

    # Sort each merged block's sessions by (room, start) so same-room sessions
    # are adjacent and ordered chronologically within the room.
    for block in merged:
        block["sessions"].sort(key=lambda s: (s["room"], s["start_local"]))

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

    header_accordion_name = f"acc-h-{anchor}"
    header_cells = "".join(
        f"<div class='col'>{render_col_header(s, header_accordion_name)}</div>"
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


SHORT_DAY = {
    "Monday": "Mon", "Tuesday": "Tues", "Wednesday": "Weds", "Thursday": "Thurs",
    "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun",
}


def render_tabs(data: dict) -> str:
    """One link per day, plus an About button on the right."""
    tabs = []
    for day in data["days"]:
        color = DAY_COLORS.get(day["day_name"], DAY_COLORS["Monday"])
        anchor = day_anchor(day["date"])
        short = SHORT_DAY.get(day["day_name"], day["day_name"])
        tabs.append(
            f"<a class='tab' href='#{anchor}' "
            f"style='background:{color['bar']}; color:{color['fg']};'>"
            f"{escape(short)}</a>"
        )
    about_btn = (
        "<button class='tab tab-about' id='about-trigger'>About…</button>"
    )
    return f"<nav class='tab-bar'>{''.join(tabs)}{about_btn}</nav>"


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
  display: flex; align-items: center; gap: 12px;
}
header.page-header h1 { margin: 0; font-size: 18px; font-weight: 600; flex: 1 1 auto; }
header.page-header .subtitle { font-size: 12px; opacity: 0.8; margin-top: 2px; }
.tab-about {
  background: #444; color: #fff;
  cursor: pointer; border: none;
  flex: 0 0 auto;  /* don't expand to fill like day tabs */
  margin-left: auto;  /* push to the right */
}
.tab-about:hover { filter: brightness(1.2); }

.about-dialog {
  border: none; border-radius: 8px;
  padding: 24px 28px;
  max-width: 90%; width: 420px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
  font-size: 14px; line-height: 1.5;
}
.about-dialog::backdrop { background: rgba(0,0,0,0.4); }
.about-dialog p { margin: 0 0 14px; }
.about-signature { font-style: italic; color: #555; }
.about-dialog-actions { display: flex; justify-content: flex-end; }
.about-close {
  padding: 8px 16px; border-radius: 4px;
  border: 1px solid #ccc; background: #f5f5f5; color: #333;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.about-close:hover { background: #eee; }
.tab-bar {
  position: sticky; top: 0; z-index: 200;
  background: #ffffff; border-bottom: 1px solid #ddd;
  padding: 8px 12px;
  display: flex; gap: 8px; flex-wrap: nowrap;
}
.tab {
  display: inline-block; padding: 6px 8px; border-radius: 4px;
  text-decoration: none; font-size: 13px; font-weight: 600;
  flex: 1 1 0; text-align: center;
  max-width: 160px;
}
.tab:hover { opacity: 0.85; }

section.block { margin: 24px 0; position: relative; }
section.block:first-of-type { margin-top: 0; }
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
  border-bottom: 1px solid #ccc;
  font-size: 11px;
  cursor: pointer;
}
.col-header-summary {
  list-style: none;
  padding: 6px 8px;
  height: 80px;
  display: flex; flex-direction: column;
}
.col-header-summary::-webkit-details-marker { display: none; }
.col-header[open] {
  background: #fff;
  border-bottom: 2px solid #555;
  position: relative;
  z-index: 6;  /* above sibling headers, below tab bar */
}
.col-header[open] .col-header-summary { height: auto; }
.col-room {
  font-weight: 700; color: #444;
  font-size: 13px;
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
.col-header[open] .col-title {
  -webkit-line-clamp: unset;
  line-clamp: unset;
  overflow: visible;
}
.col-chairs-suffix { font-weight: 400; color: #777; }
.col-header-detail {
  padding: 6px 8px 10px;
  border-top: 1px solid rgba(0,0,0,0.12);
  font-size: 12px; line-height: 1.4;
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

/* Sticky donation bar pinned to the bottom of the viewport. */
.donate-bar {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: #f4b400; color: #2a2a2a;
  padding: 14px 16px;
  text-align: center;
  font-size: 15px; font-weight: 700;
  box-shadow: 0 -2px 8px rgba(0,0,0,0.2);
  z-index: 300;
  border-top: 2px solid #c68f00;
}
.donate-link {
  color: #2a2a2a; text-decoration: none;
  display: inline-block; padding: 2px 0;
}
.donate-link:hover { text-decoration: underline; }
/* Leave room at the bottom of the page so the donate bar doesn't cover content. */
main { padding-bottom: 70px; }

/* Donation confirmation dialog */
.donate-dialog {
  border: none; border-radius: 8px;
  padding: 20px 24px;
  max-width: 90%; width: 360px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
  font-size: 14px; line-height: 1.4;
}
.donate-dialog::backdrop { background: rgba(0,0,0,0.4); }
.donate-dialog h3 { margin: 0 0 10px; font-size: 16px; }
.donate-dialog p { margin: 0 0 18px; }
.donate-dialog-actions {
  display: flex; gap: 8px; justify-content: flex-end;
}
.donate-cancel, .donate-continue {
  padding: 8px 14px; border-radius: 4px;
  font-size: 13px; font-weight: 600;
  border: 1px solid #ccc;
  background: #f5f5f5; color: #333;
  text-decoration: none; cursor: pointer;
}
.donate-continue {
  background: #f4b400; color: #2a2a2a; border-color: #c68f00;
}
.donate-cancel:hover { background: #eee; }
.donate-continue:hover { filter: brightness(1.1); }
"""


SCROLL_SYNC_JS = """
// (1) Sync each block's header row horizontal scroll to its body row's scroll.
// (2) When a cell opens, grow its .col-body to accommodate the expanded cell
//     so the document reflows naturally (next block pushed down). Restore
//     original height on close.
// (3) Close any open cell when the page scrolls vertically beyond a threshold.
(function () {
  document.querySelectorAll('section.block').forEach(function (block) {
    var body = block.querySelector('.body-scroll');
    var header = block.querySelector('.header-wrap');
    if (!body || !header) return;
    body.addEventListener('scroll', function () {
      header.scrollLeft = body.scrollLeft;
    }, { passive: true });
  });

  // Track the open cell so we can grow/restore its column body.
  var openCell = null;
  var openAtY = 0;
  var grownColBody = null;
  var originalColHeight = '';

  function growColBodyFor(cell) {
    var colBody = cell.closest('.col-body');
    if (!colBody) return;
    // Cell's top offset is from its inline style. We want the col-body to
    // contain the cell's full extent: top + offsetHeight + small breathing room.
    var topPx = parseFloat(cell.style.top) || 0;
    var needed = topPx + cell.offsetHeight + 8;
    // Only grow; never shrink below the original block-proportional height.
    var orig = parseFloat(colBody.style.height) || 0;
    if (needed > orig) {
      grownColBody = colBody;
      originalColHeight = colBody.style.height;
      colBody.style.height = needed + 'px';
    }
  }

  function restoreColBody() {
    if (grownColBody) {
      grownColBody.style.height = originalColHeight;
      grownColBody = null;
      originalColHeight = '';
    }
  }

  document.addEventListener('toggle', function (e) {
    if (!e.target.matches('details.cell')) return;
    if (e.target.open) {
      // Restore any previously-grown col-body first (exclusive accordion).
      restoreColBody();
      openCell = e.target;
      openAtY = window.scrollY;
      // Let the browser finish reflowing the cell to its open size before measuring.
      requestAnimationFrame(function () {
        if (openCell === e.target) growColBodyFor(e.target);
      });
    } else if (e.target === openCell) {
      restoreColBody();
      openCell = null;
    }
  }, true);

  window.addEventListener('scroll', function () {
    if (openCell && Math.abs(window.scrollY - openAtY) > 20) {
      var c = openCell;
      openCell = null;
      restoreColBody();
      c.open = false;
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
</header>

<dialog id="about-dialog" class="about-dialog">
  <p>My dearest water nerds:</p>
  <p>I am a grumpy, aging SFS member who can't navigate an SFS meeting without The Grid.
     These newfangled "apps" and "favorite" buttons aren't compatible with my diminished intellect or my iPhone 6s.</p>
  <p>This page is my offering to other grumpy old SFS members in hopes it will help
     restore some lost sanity. I also hope that it helps younger SFS members realize that
     all we really need when navigating life is a sense of where we want to be and
     when we want to be there.</p>
  <p>If you find this combobulation of space and time useful, I ask only that you make
     a donation to support the younger and less grumpy SFS members, by clicking the
     link at the bottom of the page.</p>
  <p>Every donation will make me a little less grumpy.</p>
  <p>This society is amazing. I love you all.</p>
  <p class="about-signature">—Grumpy</p>
  <form method="dialog" class="about-dialog-actions">
    <button value="close" class="about-close">Close</button>
  </form>
</dialog>
{tabs}
<main>
{blocks_html}
</main>

<div class="donate-bar">
  <a class="donate-link" href="#" id="donate-trigger">Like this? Donate to support SFS students →</a>
</div>

<dialog id="donate-dialog" class="donate-dialog">
  <h3>Almost there!</h3>
  <p>On the next page, please select the
     <strong>SFS Student and Early Career Enrichment Fund</strong> from the dropdown.</p>
  <form method="dialog" class="donate-dialog-actions">
    <button value="cancel" class="donate-cancel">Cancel</button>
    <a class="donate-continue" href="https://www.zeffy.com/en-US/donation-form/society-for-freshwater-science--2026">Continue →</a>
  </form>
</dialog>

<script>{SCROLL_SYNC_JS}</script>
<script>
  (function () {{
    // Donate dialog
    var donateTrigger = document.getElementById('donate-trigger');
    var donateDialog = document.getElementById('donate-dialog');
    if (donateTrigger && donateDialog) {{
      donateTrigger.addEventListener('click', function (e) {{
        e.preventDefault();
        donateDialog.showModal();
      }});
      donateDialog.addEventListener('click', function (e) {{
        if (e.target === donateDialog) donateDialog.close();
      }});
    }}

    // About dialog
    var aboutTrigger = document.getElementById('about-trigger');
    var aboutDialog = document.getElementById('about-dialog');
    if (aboutTrigger && aboutDialog) {{
      aboutTrigger.addEventListener('click', function (e) {{
        e.preventDefault();
        aboutDialog.showModal();
      }});
      aboutDialog.addEventListener('click', function (e) {{
        if (e.target === aboutDialog) aboutDialog.close();
      }});
    }}
  }})();
</script>
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
