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

## Workflow

`.github/workflows/pages.yml`: cron `30 4 * * *` UTC (≈ 06:30 NL in summer) +
`workflow_dispatch`. Steps: checkout → setup uv → `uv sync --extra image` →
`surfwa web` with `TZ=Europe/Amsterdam` (pipeline uses naive local time; runner
is UTC) → `actions/upload-pages-artifact` → `actions/deploy-pages`. No secrets:
all data sources are keyless. A failed run leaves the previous deploy live.

One-time repo setting: Pages → Source: GitHub Actions.

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
