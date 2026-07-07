from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path

from surfwa.fetch.buienradar import coastal_wind
from surfwa.pipeline import PipelineCapture, run_pipeline
from surfwa.render.chart import (
    ChartUnavailableError,
    _day_label,
    assemble_days,
    render_chart,
    stars,
)
from surfwa.score import Window
from surfwa.spots import SpotConfig

_CSS = """
:root {
  --ground: #f4f6f7; --card: #ffffff; --ink: #1d2a30; --muted: #5c6e77;
  --accent: #2a6b9c; --line: #d8dfe3;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ground: #14191c; --card: #1d2429; --ink: #e4e9eb; --muted: #93a3ab;
    --accent: #6aa8d4; --line: #2c363c;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--ground); color: var(--ink); margin: 0;
  font: 16px/1.55 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  padding: 2rem 1rem 3.5rem;
}
main { max-width: 940px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.4rem; }
.eyebrow {
  color: var(--accent); font-size: 0.78rem; font-weight: 600;
  letter-spacing: 0.09em; text-transform: uppercase; margin: 0 0 0.3rem;
}
h1 { font-size: 1.8rem; margin: 0; letter-spacing: -0.01em; }
h2 { font-size: 1.05rem; margin: 0 0 0.3rem; }
.liveline { color: var(--muted); margin: 0.35rem 0 0; font-size: 0.95rem; }
.day { border-top: 1px solid var(--line); padding-top: 1.1rem; }
.row { display: flex; gap: 0.75rem; align-items: baseline; flex-wrap: wrap; padding: 0.25rem 0; }
.when {
  font-variant-numeric: tabular-nums; color: var(--accent); font-weight: 600;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.88rem;
  min-width: 4.2rem;
}
.what { flex: 1 1 20rem; }
.what small { color: var(--muted); display: block; }
.none { color: var(--muted); }
.chartcard {
  background: #ffffff; border: 1px solid var(--line); border-radius: 6px;
  padding: 0.7rem; overflow-x: auto;
}
.chartcard img { display: block; max-width: 100%; height: auto; margin: 0 auto; }
.problems { color: var(--muted); font-size: 0.85rem; }
.problems li { margin: 0.15rem 0; }
footer { color: var(--muted); font-size: 0.82rem; }
"""


def digest(
    windows: list[Window], per_day: int = 3
) -> list[tuple[date, list[Window]]]:
    by_day: dict[date, list[Window]] = {}
    for window in windows:
        by_day.setdefault(window.start.date(), []).append(window)

    result: list[tuple[date, list[Window]]] = []
    for day in sorted(by_day):
        picked: list[Window] = []
        seen: set[str] = set()
        for window in sorted(by_day[day], key=lambda w: -w.peak_score):
            if window.spot_slug in seen:
                continue
            picked.append(window)
            seen.add(window.spot_slug)
            if len(picked) == per_day:
                break
        result.append((day, picked))
    return result


def render_html(
    digest_days: list[tuple[date, list[Window]]],
    spots: dict[str, SpotConfig],
    live: dict[str, tuple[int, str]] | None,
    problems: list[str],
    generated: datetime,
    chart_file: str | None,
) -> str:
    liveline = ""
    if live:
        wind = ", ".join(f"{k} {d} {b}bft" for k, (b, d) in live.items())
        liveline = f'<p class="liveline">Actuele wind: {escape(wind)}</p>'

    if digest_days:
        day_sections = "\n".join(
            _day_section(day, windows, spots) for day, windows in digest_days
        )
    else:
        day_sections = '<section class="day"><p class="none">geen surf in de komende dagen</p></section>'

    chart = ""
    if chart_file:
        chart = (
            '<figure class="chartcard" style="margin:0">'
            f'<img src="{escape(chart_file)}" alt="surfwa forecast chart: golfhoogte, wind, getij en surfvensters per dag">'
            "</figure>"
        )

    problem_list = ""
    if problems:
        items = "\n".join(f"<li>{escape(p)}</li>" for p in problems)
        problem_list = f'<ul class="problems">{items}</ul>'

    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>surfwa</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<header>
<p class="eyebrow">surfwa &middot; dagupdate</p>
<h1>Surfvoorspelling</h1>
{liveline}
</header>
{day_sections}
{chart}
{problem_list}
<footer>Gegenereerd {generated.strftime("%d-%m-%Y %H:%M")} &middot; bronnen: Open-Meteo, Rijkswaterstaat, Buienradar</footer>
</main>
</body>
</html>
"""


def build_site(
    spots: dict[str, SpotConfig],
    days: int = 3,
    out_dir: Path = Path("site"),
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    capture = PipelineCapture()
    windows, problems = run_pipeline(spots, days=days, capture=capture)

    live = None
    try:
        live = coastal_wind()
    except Exception:
        problems.append("buienradar: actuele wind niet beschikbaar")

    chart_file = None
    try:
        render_chart(assemble_days(capture, windows, spots), spots, out_dir / "chart.png")
        chart_file = "chart.png"
    except ChartUnavailableError as exc:
        problems.append(f"geen grafiek: {exc}")

    index = out_dir / "index.html"
    index.write_text(
        render_html(digest(windows), spots, live, problems, datetime.now(), chart_file),
        encoding="utf-8",
    )
    return index


def _day_section(day: date, windows: list[Window], spots: dict[str, SpotConfig]) -> str:
    rows = []
    for w in windows:
        spot = spots[w.spot_slug]
        detail = f"{w.avg_height_m}m @ {w.avg_period_s}s &middot; {escape(w.wind_desc)} &middot; {escape(w.board)}"
        if w.warnings:
            detail += f" &middot; ! {escape(w.warnings[0])}"
        rows.append(
            '<div class="row">'
            f'<span class="when">{w.start.hour}-{w.end.hour}u</span>'
            f'<span class="what">{escape(spot.name)} {stars(w.peak_score)}'
            f"<small>{detail}</small></span>"
            "</div>"
        )
    body = "\n".join(rows) if rows else '<p class="none">geen surf</p>'
    return f'<section class="day"><h2>{_day_label(day)}</h2>\n{body}\n</section>'
