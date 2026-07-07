from __future__ import annotations

from pathlib import Path

from surfwa.pipeline import run_pipeline
from surfwa.render.structured import render_windows
from surfwa.spots import SpotConfig


def run_backtest(
    spots: dict[str, SpotConfig],
    date_str: str,
    update_file: str | None,
) -> str:
    windows, problems = run_pipeline(
        spots,
        start_date=date_str,
        end_date=date_str,
        use_nowcast=False,
    )
    rendered = render_windows(windows, spots, problems, None)

    if update_file:
        rendered += "\n\n=== Referentie ===\n"
        rendered += Path(update_file).read_text(encoding="utf-8")

    return rendered
