# SFS 2026 Concurrent Session Grid

Static HTML grid of SFS 2026 concurrent sessions, scraped from
`https://sfs-2026.m.asnevents.com.au/schedule`. Published via GitHub Pages.

**Live site**: `docs/index.html` (served by GitHub Pages from the `docs/` folder).

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
