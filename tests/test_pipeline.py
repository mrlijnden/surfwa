from datetime import datetime, timedelta
from unittest.mock import patch

from surfwa.fetch.openmeteo import HourlyConditions
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
    )
}


def _good_hours(*args, **kwargs):
    t0 = datetime(2026, 7, 6, 12)
    return [
        HourlyConditions(
            time=t0 + timedelta(hours=i),
            wave_height_m=1.0,
            wave_period_s=6.5,
            wave_direction_deg=300,
            swell_height_m=0.7,
            swell_period_s=7.0,
            swell_direction_deg=300,
            wind_speed_bft=2,
            wind_direction_deg=120,
        )
        for i in range(4)
    ]


@patch("surfwa.pipeline.latest_buoy_hm0", return_value=None)
@patch("surfwa.pipeline.tide_extremes", return_value=[])
@patch("surfwa.pipeline.fetch_tide_curve", return_value=[(datetime(2026, 7, 6, 0), 0)])
@patch("surfwa.pipeline.fetch_hourly", side_effect=_good_hours)
def test_pipeline_produces_windows(mock_fetch, *_):
    from surfwa.pipeline import run_pipeline

    windows, problems = run_pipeline(SPOTS, days=1)

    assert len(windows) == 1
    assert windows[0].spot_slug == "testspot"
    assert problems == []


@patch("surfwa.pipeline.latest_buoy_hm0", return_value=None)
@patch("surfwa.pipeline.tide_extremes", return_value=[])
@patch("surfwa.pipeline.fetch_tide_curve", return_value=[])
@patch("surfwa.pipeline.fetch_hourly", side_effect=RuntimeError("api down"))
def test_pipeline_reports_problems_not_crash(*_):
    from surfwa.pipeline import run_pipeline

    windows, problems = run_pipeline(SPOTS, days=1)

    assert windows == []
    assert "testspot" in problems[0]


@patch("surfwa.pipeline.latest_buoy_hm0", return_value=None)
@patch("surfwa.pipeline.tide_extremes", return_value=[])
@patch("surfwa.pipeline.fetch_tide_curve", return_value=[])
@patch("surfwa.pipeline.fetch_hourly", return_value=[])
def test_pipeline_reports_empty_wave_data_as_problem(*_):
    from surfwa.pipeline import run_pipeline

    windows, problems = run_pipeline(SPOTS, days=1)

    assert windows == []
    assert "golfdata leeg" in problems[0]


@patch("surfwa.pipeline.latest_buoy_hm0", return_value=None)
@patch("surfwa.pipeline.tide_extremes", return_value=[])
@patch("surfwa.pipeline.fetch_tide_curve", return_value=[])
@patch("surfwa.pipeline.fetch_hourly", side_effect=_good_hours)
def test_pipeline_reports_empty_tide_data_but_keeps_windows(*_):
    from surfwa.pipeline import run_pipeline

    windows, problems = run_pipeline(SPOTS, days=1)

    assert len(windows) == 1
    assert "getijdata leeg" in problems[0]


def test_render_contains_spot_and_times():
    from surfwa.pipeline import run_pipeline
    from surfwa.render.structured import render_windows, windows_to_json

    with (
        patch("surfwa.pipeline.fetch_hourly", side_effect=_good_hours),
        patch("surfwa.pipeline.fetch_tide_curve", return_value=[(datetime(2026, 7, 6, 0), 0)]),
        patch("surfwa.pipeline.tide_extremes", return_value=[]),
        patch("surfwa.pipeline.latest_buoy_hm0", return_value=None),
    ):
        windows, problems = run_pipeline(SPOTS, days=1)
    text = render_windows(windows, SPOTS, problems, None)
    js = windows_to_json(windows)

    assert "Testspot" in text and "12-16u" in text
    assert '"testspot"' in js and '"12:00"' in js
