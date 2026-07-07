from datetime import date
from pathlib import Path
from unittest.mock import patch

from surfwa.cli import main
from surfwa.render.chart import ChartUnavailableError


def _run(argv, **overrides):
    patches = {
        "run_pipeline": patch("surfwa.cli.run_pipeline", return_value=([], [])),
        "coastal_wind": patch(
            "surfwa.fetch.buienradar.coastal_wind", side_effect=RuntimeError("down")
        ),
        "assemble_days": patch(
            "surfwa.render.chart.assemble_days", return_value=[]
        ),
        "render_chart": patch("surfwa.render.chart.render_chart"),
    }
    mocks = {}
    with patch("sys.argv", ["surfwa", *argv]):
        started = []
        try:
            for name, p in patches.items():
                mocks[name] = p.start()
                started.append(p)
            if "render_chart" in overrides:
                mocks["render_chart"].side_effect = overrides["render_chart"]
            else:
                mocks["render_chart"].side_effect = lambda days, spots, out: out
            main()
        finally:
            for p in started:
                p.stop()
    return mocks


def test_update_image_passes_capture_and_writes_chart(tmp_path, capsys):
    out = tmp_path / "chart.png"

    mocks = _run(["update", "--no-llm", "--image", str(out)])

    assert mocks["run_pipeline"].call_args.kwargs["capture"] is not None
    assert mocks["render_chart"].call_args.args[2] == out
    assert str(out) in capsys.readouterr().out


def test_update_without_image_skips_capture(capsys):
    mocks = _run(["update", "--no-llm"])

    assert mocks["run_pipeline"].call_args.kwargs["capture"] is None
    mocks["render_chart"].assert_not_called()


def test_update_image_default_filename(capsys):
    mocks = _run(["update", "--no-llm", "--image"])

    out = mocks["render_chart"].call_args.args[2]
    assert out == Path(f"surfwa-{date.today().isoformat()}.png")


def test_web_subcommand_calls_build_site(tmp_path, capsys):
    out = tmp_path / "site" / "index.html"
    with (
        patch("sys.argv", ["surfwa", "web", "--days", "2", "--out", str(tmp_path / "site")]),
        patch("surfwa.render.web.build_site", return_value=out) as build,
    ):
        main()

    assert build.call_args.kwargs["days"] == 2
    assert build.call_args.kwargs["out_dir"] == tmp_path / "site"
    assert str(out) in capsys.readouterr().out


def test_update_image_degrades_when_matplotlib_missing(capsys):
    def unavailable(days, spots, out):
        raise ChartUnavailableError("matplotlib ontbreekt; uv sync --extra image")

    _run(["update", "--no-llm", "--image"], render_chart=unavailable)

    output = capsys.readouterr().out
    assert "uv sync --extra image" in output
    assert "surfwa update" in output
