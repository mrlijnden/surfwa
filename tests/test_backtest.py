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


def _historical_hours(*args, **kwargs):
    assert kwargs["start_date"] == "2026-07-03"
    assert kwargs["end_date"] == "2026-07-03"
    t0 = datetime(2026, 7, 3, 19)
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
        for i in range(3)
    ]


def test_run_backtest_replays_date_and_appends_reference_update(tmp_path):
    from surfwa.backtest import run_backtest

    reference = tmp_path / "referentie.md"
    reference.write_text("oude referentie update\n", encoding="utf-8")

    with (
        patch("surfwa.pipeline.fetch_hourly", side_effect=_historical_hours),
        patch(
            "surfwa.pipeline.fetch_tide_curve",
            return_value=[(datetime(2026, 7, 3, 18), 0)],
        ),
        patch("surfwa.pipeline.tide_extremes", return_value=[]),
        patch(
            "surfwa.pipeline.latest_buoy_hm0",
            side_effect=AssertionError("backtest must not use nowcast"),
        ),
    ):
        text = run_backtest(SPOTS, "2026-07-03", str(reference))

    assert "Testspot" in text
    assert "19-22u" in text
    assert "\n\n=== Referentie ===\noude referentie update\n" in text
