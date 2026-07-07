# surfwa — personal surf-update generator

**Date:** 2026-07-06 (revised 2026-07-07: forecast chart, uv packaging, README)
**Status:** approved design, pre-implementation

## Goal

A personal, on-demand Python CLI that fetches the coming 3 days of wave, wind, and
tide data for Zuid- and Noord-Holland surf spots, scores surfable time windows per
spot using a hand-maintained per-spot rule base, and renders the result as a Dutch
prose surf update (via `codex exec`), a structured windows table, and optionally a
forecast chart PNG.

## Constraints

- **No paid APIs.** All data sources are free and keyless: Open-Meteo, RWS DD-API
  2.0, Buienradar, later KNMI Open Data (free key).
- **Prose via `codex exec`** (OpenAI Codex CLI, non-interactive). No Anthropic
  API key required. Must degrade gracefully when `codex` is unavailable.
- **uv-managed project.** `pyproject.toml` + committed `uv.lock`; installed and
  run via `uv sync` / `uv run surfwa`.

## Spot coverage

Zuid-Holland: Maasvlakte (P3–P6), Hoek van Holland, Ter Heijde/Kijkduin,
Scheveningen (Noord + Zuid), Wassenaar, Katwijk, Noordwijk.
Noord-Holland: Zandvoort, IJmuiden, Wijk aan Zee (+ Wijk Dorp), Castricum,
Egmond, Bergen, Camperduin, Petten.

## Data sources (all verified 2026-07-06 unless noted)

| Source | Role | Endpoint | Verified |
|---|---|---|---|
| Open-Meteo Marine | Hourly wave forecast per spot: height, period, direction, swell vs wind-sea split | `marine-api.open-meteo.com/v1/marine` | ✅ |
| Open-Meteo Marine historical | Same variables, decades back (ERA5) — backtest fuel | same, with `start_date`/`end_date` | ✅ |
| Open-Meteo weather | Hourly wind forecast (speed, direction, gusts) | `api.open-meteo.com/v1/forecast` | assumed (same provider) |
| RWS DD-API 2.0 | Measured wave height/period (buoys: `ijgeul.2.boei`, `europlatform.3`, K13), water levels, astronomical tide; live + historical | `ddapi20-waterwebservices.rijkswaterstaat.nl` (POST `METADATASERVICES/OphalenCatalogus`, `ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen`, needs `ProcesType`) | ✅ |
| Buienradar | Live measured coastal wind (IJmuiden, Hoek van Holland, …) | `data.buienradar.nl/2.0/feed/json` | ✅ |
| KNMI Open Data | Phase-2 upgrade: Harmonie-AROME high-res wind forecast | needs free API key | not yet |
| Webcams | Later phase: visual validation of predicted windows | frame grab | not yet |

**Migration note:** the classic RWS WaterWebservices endpoint
(`waterwebservices.rijkswaterstaat.nl`) was retired December 2025 (301 redirect,
full shutdown April 2026). Build exclusively on the DD-API 2.0 endpoint. Location
codes are unified lowercase slugs (e.g. `hoekvanholland`, `ijgeul.2.boei`);
requests take a `ProcesType` of `meting`, astronomical, or prediction.

## Architecture

```
knowledge/spots.yaml        per-spot rule base  ← heart of the project
knowledge/updates/          optional local style examples (untracked)
        │
fetch/  ── Open-Meteo (forecast) + RWS (tide, buoys) + Buienradar (live wind)
        │        per spot: hourly series for next 3 days
score/  ── per spot per hour: wind factor × swell factor × tide factor
        │        → contiguous windows above threshold, with qualifiers
        │          (clean/choppy, board advice, spot warnings)
nowcast ── compare live buoy Hm0 vs model for the current hour; scale
        │        today's forecast by the measured ratio
render/ ── structured table | prose via `codex exec` | forecast chart PNG
backtest/── replay a past date: pull historical measurements, run scorer,
                 diff our windows against a local reference file
```

### knowledge/spots.yaml (per spot)

- coordinates (for Open-Meteo)
- RWS tide station + nearest wave buoy code
- wind sectors: offshore / cross / onshore (degrees)
- workable tide phase (e.g. Zandvoort: outer banks at low water)
- minimum surfable swell (height × period thresholds)
- special notes carried into the prose: IJmuiden pier shadow (works on W/WNW),
  Scheveningen current warning, Wijk shorebreak character, Maasvlakte P3–P5 vs P6

### CLI

```
surfwa update [--days 3] [--no-llm] [--spot NAME] [--image [PATH]]
surfwa backtest <reference-file>
```

`--no-llm` prints the structured windows table — both the fallback and the
debugging view for checking facts before style. `--image` additionally writes a
forecast chart PNG (default `surfwa-YYYY-MM-DD.png` in the current directory);
it combines freely with `--no-llm` and `--spot`.

## Forecast chart (`--image`)

`src/surfwa/render/chart.py`, entry point
`render_chart(days: list[DayData], out_path: Path) -> Path`. `DayData` bundles
what the pipeline already computes per day: date, hourly wave/wind series,
tide extremes (HW/LW from RWS), the scored windows, and the nowcast note
(e.g. "K13 nu: 1.1m 5s"). No new fetching.

One matplotlib figure, one row-block per forecast day (gridspec), per block:

1. **Wave panel** — hourly wave-height fill (m), period annotated at peaks;
   nowcast-corrected values for today.
2. **Wind row** — hourly direction arrows (quiver) colored
   offshore/cross/onshore relative to the day's best spot, Bft labels every 3 h.
3. **Tide curve** — RWS astronomical water level with HW/LW times labeled.
4. **Window bars** — one horizontal bar (broken_barh) per spot that has a
   window that day, labeled with spot name, time range, star rating, and
   qualifiers; a windowless day renders a single "geen surf" strip.

Dutch labels throughout. Figure height scales with the number of spot rows.

`matplotlib>=3.8` is an optional extra (`uv sync --extra image`). `--image`
without matplotlib installed prints an actionable error and still produces the
text output.

## Packaging & tooling (uv)

- `pyproject.toml` with `[project]` deps `requests>=2.31`, `PyYAML>=6.0`;
  optional extra `image = ["matplotlib>=3.8"]`; dev dependency group
  `pytest>=8.0`, `responses>=0.25`.
- `uv.lock` committed. Setup: `uv sync` (add `--extra image` for charts).
- Run: `uv run surfwa …`; tests: `uv run pytest`.
- Entry point `surfwa = "surfwa.cli:main"`; package layout `src/surfwa/`.

## README

Public-safe `README.md` at the repo root: what the tool is; requirements
(Python ≥ 3.12, uv; optional `codex` CLI for prose; optional `image` extra for
charts); setup (`uv sync`, no API keys needed); the CLI invocations above with
expected output; how to add or tune a spot in `knowledge/spots.yaml`; and a note
that users can drop their own example updates in `knowledge/updates/`
(untracked) to steer the prose style — without them a plain default style is
used.

## Build phases

1. **Rule base** — author `knowledge/spots.yaml` from local spot knowledge;
   reviewed by user (who knows the spots).
2. **Pipeline** — fetch + score + nowcast correction + `--no-llm` structured
   output.
3. **Prose** — prompt design + `codex exec` integration, optional style
   examples from `knowledge/updates/`.
4. **Chart** — `--image` renderer.
5. **Backtest & tune** — golden tests replaying past dates against local
   reference files; ongoing loop to refine `spots.yaml`.

## Error handling

- An unreachable API degrades to a partial update that names the missing spots/
  data; the tool never fabricates values.
- Missing `codex` binary → structured output with a notice.
- Missing matplotlib with `--image` → text output plus an install hint.
- Missing data series in the chart → panel left empty with a "geen data" note.
- RWS 204 (no data for a location/quantity combo) is expected for some stations;
  fall back to the next-nearest buoy from `spots.yaml`.

## Testing

- Unit tests on the scorer with fixture forecast series (known good/bad hours).
- Golden backtests: historical data in → our windows out, compared against local
  reference files within ±1 h tolerance.
- Prose checks: generated text mentions only spots/times present in the windows
  JSON (regex over times), guarding against LLM-invented windows.
- Chart: fixture windows/series → PNG exists, >10 KB, figure has the expected
  number of axes (no pixel-diff goldens — brittle across matplotlib versions);
  smoke test that a monkeypatched missing matplotlib degrades cleanly.

## Out of scope (YAGNI)

- Zeeland, Belgium, Wadden spots (can be added later via `spots.yaml`).
- Scheduled delivery, web UI, notifications.
- Statistical model fitting for the rule base.
