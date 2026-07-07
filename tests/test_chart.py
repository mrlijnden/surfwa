import sys
from datetime import date, datetime, timedelta

import pytest

from surfwa.fetch.openmeteo import HourlyConditions
from surfwa.fetch.rws import TideEvent
from surfwa.score import Window
from surfwa.spots import SpotConfig

SPOTS = {
    "testspot": SpotConfig(
        slug="testspot",
        name="Testspot",
        region="NH",
        lat=52.4,
        lon=4.5,
        tide_station="x",
        wave_buoy="y",
        coast_normal_deg=300,
        tide_pref="any",
        min_wave_m=0.4,
        min_period_s=5.0,
    ),
    "zuidspot": SpotConfig(
        slug="zuidspot",
        name="Zuidspot",
        region="ZH",
        lat=52.1,
        lon=4.2,
        tide_station="z",
        wave_buoy="zb",
        coast_normal_deg=290,
        tide_pref="any",
        min_wave_m=0.4,
        min_period_s=5.0,
    ),
}

DAY1 = date(2026, 7, 7)
DAY2 = date(2026, 7, 8)


def _hours(day: date, count: int = 24) -> list[HourlyConditions]:
    t0 = datetime(day.year, day.month, day.day)
    return [
        HourlyConditions(
            time=t0 + timedelta(hours=i),
            wave_height_m=1.0,
            wave_period_s=6.0,
            wave_direction_deg=300,
            swell_height_m=0.7,
            swell_period_s=7.0,
            swell_direction_deg=300,
            wind_speed_bft=3,
            wind_direction_deg=120,
        )
        for i in range(count)
    ]


def _window(slug: str, day: date, start_h: int, end_h: int, peak: float) -> Window:
    t0 = datetime(day.year, day.month, day.day)
    return Window(
        spot_slug=slug,
        start=t0 + timedelta(hours=start_h),
        end=t0 + timedelta(hours=end_h),
        peak_score=peak,
        avg_height_m=0.9,
        avg_period_s=5.5,
        wind_desc="W 3bft",
        tide_desc="falling",
        board="fish/longboard",
        warnings=["Open spot: wordt snel hotseklots"],
    )


def _capture():
    from surfwa.pipeline import PipelineCapture

    capture = PipelineCapture()
    for slug in SPOTS:
        capture.hours_by_spot[slug] = _hours(DAY1) + _hours(DAY2)
    for station in ("x", "z"):
        capture.tide_curve_by_station[station] = [
            (datetime(2026, 7, 7) + timedelta(hours=h), 60 * ((h % 12) - 6))
            for h in range(48)
        ]
        capture.extremes_by_station[station] = [
            TideEvent(time=datetime(2026, 7, 7, 6), kind="LW", level_cm=-70),
            TideEvent(time=datetime(2026, 7, 7, 12), kind="HW", level_cm=80),
        ]
    capture.buoy_readings["zb"] = (datetime(2026, 7, 7, 10), 1.1)
    return capture


def _days():
    from surfwa.render.chart import assemble_days

    windows = [
        _window("testspot", DAY1, 10, 14, 6.0),
        _window("zuidspot", DAY1, 12, 18, 7.5),
    ]
    return assemble_days(_capture(), windows, SPOTS)


def test_assemble_days_groups_windows_and_picks_best_spot():
    days = _days()

    assert [d.day for d in days] == [DAY1, DAY2]
    assert days[0].best_spot == "zuidspot"
    assert days[0].coast_normal_deg == 290
    assert [w.spot_slug for w in days[0].windows] == ["testspot", "zuidspot"]
    assert all(h.time.date() == DAY1 for h in days[0].hours)
    assert len(days[0].hours) == 24
    assert days[0].extremes and days[0].extremes[0].kind == "LW"
    assert days[1].windows == []
    assert days[1].hours


def test_assemble_days_sets_nowcast_note_on_first_day_only():
    days = _days()

    assert days[0].nowcast_note == "zb nu: 1.1m"
    assert days[1].nowcast_note is None


def test_build_figure_has_four_panels_per_day_and_geen_surf_strip():
    from surfwa.render.chart import build_figure

    fig = build_figure(_days(), SPOTS)
    try:
        assert len(fig.axes) == 8
        texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert any("geen surf" in t for t in texts)
        assert any("Zuidspot" in t for t in texts)
    finally:
        import matplotlib.pyplot as plt

        plt.close(fig)


def test_render_chart_writes_png(tmp_path):
    from surfwa.render.chart import render_chart

    out = tmp_path / "chart.png"
    result = render_chart(_days(), SPOTS, out)

    assert result == out
    assert out.exists()
    assert out.stat().st_size > 10_000


def test_render_chart_without_matplotlib_raises_actionable_error(
    tmp_path, monkeypatch
):
    from surfwa.render.chart import ChartUnavailableError, render_chart

    for mod in list(sys.modules):
        if mod.startswith("matplotlib"):
            monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setitem(sys.modules, "matplotlib", None)

    with pytest.raises(ChartUnavailableError, match="uv sync --extra image"):
        render_chart(_days(), SPOTS, tmp_path / "chart.png")
