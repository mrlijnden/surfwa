# surfwa — daily predictions page on GitHub Pages

**Date:** 2026-07-07
**Status:** approved design

## Goal

A small static page at `https://mrlijnden.github.io/surfwa/` showing every day's
predictions: date + live coastal wind header, a per-day digest of the best surf
windows, and the full forecast chart. Rebuilt every morning by a scheduled
GitHub Action running the normal pipeline.

## CLI

```
surfwa web [--days 3] [--out site]
```

New renderer `src/surfwa/render/web.py`:

- `digest(windows, per_day=3)` — group windows by start date; per day, the top 3
  windows by peak score, at most one per spot.
- `render_html(...)` — self-contained HTML (inline CSS, no JS, no external
  assets); Dutch labels; light/dark via `prefers-color-scheme`; per-day digest
  rows (time range, spot, stars, size @ period, wind, board, first warning) and
  the chart image (`chart.png` alongside `index.html`).
- `build_site(spots, days, out_dir)` — runs the pipeline with a
  `PipelineCapture`, renders chart + HTML into `out_dir`.

Degradation as elsewhere: missing data → "geen data"; chart unavailable → page
without the image; pipeline problems listed on the page. No prose on the page
(no `codex` on CI runners; deterministic output only).

## Hosting: Dokploy (nixpacks)

Deployed as a Dokploy Application built with **nixpacks** from the GitHub repo.
Repo files:

- `.python-version` → `3.12` (nixpacks' Python provider defaults to 3.11;
  surfwa requires ≥3.12).
- `nixpacks.toml` — overrides the provider's default `uv sync --no-dev --frozen`
  (which would skip the `image` extra and thus matplotlib) by mirroring it
  with `--extra image` appended; sets a POSIX `TZ` rule for CET/CEST — the
  runtime image has no tzdata, so a named zone would silently fall back to
  UTC and shift all times by 2 h; start command `sh deploy/start.sh`.
- `deploy/start.sh` — generates the site on boot, regenerates every
  `REFRESH_HOURS` (default 6; Open-Meteo updates several times a day), and
  serves the site directory with `python -m http.server` on `$PORT`
  (default 8080). A failed regeneration logs and keeps the previous page.

Dokploy setup (manual, once): Application → GitHub repo → nixpacks build →
expose port 8080 → attach domain. Verified locally first via
`nixpacks build` + `docker run` + `curl`.

The earlier GitHub Pages workflow is removed and Pages disabled; Dokploy is the
single host.

## Testing

- Digest: top-3 per day, one window per spot, day grouping.
- HTML renderer with fixture windows: expected spots/times present, chart `img`
  tag present, no unrendered placeholders.
- `build_site` writes `index.html` + `chart.png` (chart renderer mocked).
- CLI `web` subcommand wiring.
- Workflow verified once via `workflow_dispatch` after merge.

## Out of scope

- JS interactivity, spot filters, history of past days.
- Prose on the page.
