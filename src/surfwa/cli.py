from __future__ import annotations

import argparse
from pathlib import Path

from surfwa.pipeline import run_pipeline
from surfwa.render.structured import render_windows
from surfwa.spots import load_spots

ROOT = Path(__file__).resolve().parent.parent.parent
SPOTS_YAML = ROOT / "knowledge" / "spots.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(prog="surfwa")
    subcommands = parser.add_subparsers(dest="cmd", required=True)

    update = subcommands.add_parser("update", help="generate surf update")
    update.add_argument("--days", type=int, default=3)
    update.add_argument("--no-llm", action="store_true")
    update.add_argument("--spot", default=None)

    backtest = subcommands.add_parser("backtest", help="replay a historical date")
    backtest.add_argument("--date", required=True, help="YYYY-MM-DD")
    backtest.add_argument("--update", default=None, help="reference file to compare against")

    args = parser.parse_args()
    spots = load_spots(SPOTS_YAML)

    if args.cmd == "update":
        windows, problems = run_pipeline(
            spots,
            days=args.days,
            spot_filter=args.spot,
        )
        live = None
        try:
            from surfwa.fetch.buienradar import coastal_wind

            live = coastal_wind()
        except Exception:
            problems.append("buienradar: actuele wind niet beschikbaar")

        structured = render_windows(windows, spots, problems, live)
        if args.no_llm:
            print(structured)
            return

        from surfwa.render.prose import generate_update

        print(generate_update(windows, structured))
        return

    if args.cmd == "backtest":
        from surfwa.backtest import run_backtest

        print(run_backtest(spots, args.date, args.update))
