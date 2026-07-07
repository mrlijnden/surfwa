from __future__ import annotations

import json
from itertools import groupby

from surfwa.score import Window
from surfwa.spots import SpotConfig

_PHASE_NL = {
    "high": "hoogwater",
    "low": "laagwater",
    "rising": "opkomend",
    "falling": "afgaand",
    "unknown": "getij onbekend",
}


def render_windows(
    windows: list[Window],
    spots: dict[str, SpotConfig],
    problems: list[str],
    live_wind: dict[str, tuple[int, str]] | None,
) -> str:
    lines = ["surfwa update", "=" * 40]
    if live_wind:
        lines.append(
            "Actuele wind: "
            + ", ".join(f"{k} {d} {b}bft" for k, (b, d) in live_wind.items())
        )
    for day, group in groupby(
        sorted(windows, key=lambda w: (w.start.date(), w.spot_slug)),
        key=lambda w: w.start.date(),
    ):
        lines.append(f"\n## {day.strftime('%A %d %B')}")
        for window in group:
            spot = spots[window.spot_slug]
            lines.append(
                f"  {spot.name:<28} {_hhu(window):>9}  "
                f"score {window.peak_score:>4}  "
                f"{window.avg_height_m}m @ {window.avg_period_s}s  "
                f"{window.wind_desc}  {_PHASE_NL[window.tide_desc]}  "
                f"[{window.board}]"
            )
            for warning in window.warnings:
                lines.append(f"  {'':<28} ! {warning}")
    if not windows:
        lines.append("\nGeen surfbare windows gevonden.")
    for problem in problems:
        lines.append(f"\n! {problem}")
    return "\n".join(lines)


def windows_to_json(windows: list[Window]) -> str:
    return json.dumps(
        [
            {
                "spot": window.spot_slug,
                "date": window.start.date().isoformat(),
                "start": window.start.strftime("%H:%M"),
                "end": window.end.strftime("%H:%M"),
                "peak_score": window.peak_score,
                "height_m": window.avg_height_m,
                "period_s": window.avg_period_s,
                "wind": window.wind_desc,
                "tide": window.tide_desc,
                "board": window.board,
                "warnings": window.warnings,
            }
            for window in windows
        ],
        ensure_ascii=False,
        indent=1,
    )


def _hhu(window: Window) -> str:
    return f"{window.start.hour}-{window.end.hour}u"
