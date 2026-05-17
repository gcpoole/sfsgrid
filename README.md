# SFS 2026 Concurrent Session Grid

Static HTML grid of SFS 2026 concurrent sessions, scraped from
`https://sfs-2026.m.asnevents.com.au/schedule`. Published via GitHub Pages.

**Live site**: `docs/index.html` (served by GitHub Pages from the `docs/` folder).

> **Local working copy lives at:** `~/claude_working_dir/sfs2026_schedule/`

## Layout

```
.
├── docs/index.html              # The published artifact (GitHub Pages serves this)
├── sfs2026_schedule.json        # Canonical schedule data
├── raw_html/
│   ├── full_schedule.html       # Conference-wide listing page
│   └── sessions/<id>.html       # One file per chaired session
├── parse_schedule.py            # raw_html → schedule.json (session skeleton)
├── fetch_sessions.py            # Downloads each session detail page
├── parse_presentations.py       # Adds presentations[] to schedule.json
├── add_durations.py             # Adds end_time + duration_min to each presentation
├── survey_sessions.py           # Categorizes session pages (finds edge cases)
├── generate_grid.py             # schedule.json → docs/index.html
└── .venv/                       # Local venv (ignored)
```

## To regenerate from scratch (e.g., next year)

```bash
# 1. Set up venv (uses miniconda's Python; see notes below)
/home/goff/miniconda3/bin/python3 -m venv .venv
./.venv/bin/pip install beautifulsoup4

# 2. Download the conference-wide listing
curl -sS -A "Mozilla/5.0" "https://sfs-XXXX.m.asnevents.com.au/schedule" \
  -o raw_html/full_schedule.html

# 3. Parse session skeleton
./.venv/bin/python parse_schedule.py

# 4. Fetch each session page (rate-limited; ~2 min)
./.venv/bin/python fetch_sessions.py

# 5. (Optional) survey for new edge cases
./.venv/bin/python survey_sessions.py

# 6. Parse presentations into sfs2026_schedule.json
./.venv/bin/python parse_presentations.py

# 7. Add durations
./.venv/bin/python add_durations.py

# 8. Generate the HTML
./.venv/bin/python generate_grid.py
```

## To regenerate just the HTML (after editing the JSON)

```bash
./.venv/bin/python generate_grid.py
```

## To publish

Commit and push `docs/index.html`. GitHub Pages serves from `main` branch, `/docs` folder.

## HTML structure — why it's built this way

Several non-obvious design decisions were forced by CSS layout constraints.
Documenting them so future-you (or a future maintainer) can change things
without breaking what works.

### Time-proportional cells

Each cell is `position: absolute` inside a fixed-height `.col-body`. The
cell's `top` and `--collapsed-height` (a CSS variable) are computed from
the presentation's start time and duration. `8px = 1 min` is set as the
default scale; a 4-minute lightning talk is ~32px tall, a 15-min talk is
120px tall. The scale was picked so the shortest real slot (4 min) fits
one line of body text.

### Sticky cap, separate scroll container

The block header ("Monday, May 18 · 11:00 AM–12:30 PM" plus the column-
header row) is in a `<div class="block-cap">` that sits **outside** the
horizontal scroll container, as a direct child of `<section class="block">`.
This is critical: vertical `position: sticky` only works against the
nearest scrolling ancestor. If the cap were inside a horizontally-
scrolling `<div>`, vertical sticky would silently fail. By keeping the
cap as a sibling (not a descendant) of the scroller, it pins cleanly to
the viewport top — same trick the global tab bar uses.

### Horizontal scroll on `.body-row`, not `.body-wrap`

`overflow-x: auto` on an element coerces `overflow-y` to non-`visible`
too (CSS spec quirk). That means a cell can't escape its scrolling
ancestor on the perpendicular axis. We put the horizontal scroll on
the innermost `.body-scroll` and leave `.body-wrap` overflow-visible,
so an expanded cell at the bottom of a block can poke downward into
the next block's space.

### Header row scroll-sync (JS shim)

Since the cap (with the column headers) is *outside* the horizontal
scroller, it doesn't horizontally scroll with the cells beneath it.
A 6-line JS shim listens for scroll on `.body-scroll` and sets
`.header-wrap.scrollLeft = body.scrollLeft` so the header columns stay
aligned with their cells. This only fires during horizontal drag, so
it doesn't trigger mobile scroll-jumpiness the way a JS-driven
vertical-sticky implementation would.

### Cell open: grow-in-place, not overlay

An open `<details class="cell">` keeps `top` fixed but changes `height`
from `var(--collapsed-height)` to `auto` so the cell grows downward
to fit its content. A small JS handler measures the open cell, then
sets `.col-body`'s `height` to accommodate so the document reflows —
the next block pushes down rather than the cell pushing into nothing.

### Stacking contexts (z-index gotchas)

The original "open cell appears under the next block" bug was a
stacking-context issue, not a clipping issue. CSS `:has()` is used
to lift the entire `<section class="block">` to `z-index: 100`
*while* it contains an open cell — without `:has()`, the section's
descendants couldn't paint over a sibling section's contents no
matter their z-index. The tab bar sits at `z-index: 200` so it
remains above any open cell.

### Exclusive accordion via `<details name="...">`

Every cell within a block shares the same `<details name="acc-...">`
attribute. The browser auto-closes other `<details>` with the same
name when one is opened. No JS needed for this — modern HTML
feature. Same trick used for the column-header `<details>`.

### Close-on-scroll

Once a cell is open it floats above the sticky cap (z-30 within
its lifted section). To make sure it doesn't stay floating forever
while the user scrolls past, a JS listener tracks `window.scrollY`
at open-time and closes the cell once the user scrolls >20px.

### Per-day color palette

The `DAY_COLORS` dict in `generate_grid.py` maps each weekday to
four shades: bar (saturated, used in the block-bar and tab button),
cell background (very pale tint of the bar), border (mid tint),
and a hover state. This gives each day a coherent visual identity
without overwhelming the data.

## Hosting & domain setup

The site lives at **https://sfsgrid.org** (custom domain) and at the default
GitHub Pages URL **https://gcpoole.github.io/sfsgrid/**. Both work; GitHub
handles the redirect from the .io URL to the custom domain.

### GitHub Pages

- Repo: https://github.com/gcpoole/sfsgrid (public)
- Pages settings (Settings → Pages):
  - **Source**: Deploy from a branch
  - **Branch**: `main`
  - **Folder**: `/docs`
  - **Custom domain**: `sfsgrid.org`
  - **Enforce HTTPS**: enabled (after the Let's Encrypt cert provisioned)
- The `docs/CNAME` file contains the custom domain string. Don't delete it;
  GitHub Pages reads it to know which domain to serve. (Our `generate_grid.py`
  only touches `docs/index.html`, so it's safe.)

### Domain registration

Domain `sfsgrid.org` is registered through **Cloudflare Registrar** (at-cost
pricing, free WHOIS privacy, no upselling). Renews annually at the same price.

### DNS records (managed at Cloudflare)

Five records, all set to **DNS only** (grey cloud — NOT proxied). Proxying
through Cloudflare's CDN can interfere with GitHub's Let's Encrypt cert
provisioning, so we leave it off.

| Type | Name | Content |
|------|------|---------|
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |
| CNAME | www | gcpoole.github.io |

These IPs are GitHub Pages' static addresses. If GitHub ever changes them,
their docs at https://docs.github.com/en/pages will list the current ones.

### Re-deploying after content changes

1. Edit data or text as needed.
2. Run `./.venv/bin/python generate_grid.py` to regenerate `docs/index.html`.
3. `git add -A && git commit -m "..." && git push`.
4. GitHub Pages rebuilds in ~30 seconds. Hard-reload the browser to bypass cache.

### Notes for next year's organizer

- Repo can be forked or copied. Change the conference URL in `parse_schedule.py`,
  re-run the scrape pipeline, regenerate.
- The custom domain can be transferred to a new repo (same owner) by changing
  the Pages custom-domain setting and updating the `docs/CNAME` file. If a
  different person takes over, they'd need to either get added as a repo
  collaborator or own the domain themselves.
- The donation link in `generate_grid.py` points directly to the SFS Zeffy
  form. If SFS changes platforms, update the URL there.
