from datetime import date, datetime
from math import inf, nan

import pytest

from surfwa.fetch.openmeteo import HourlyConditions
from surfwa.nowcast import apply_correction, correction_ratio


@pytest.mark.parametrize(
    ("measured_m", "model_m", "expected"),
    [
        (0.5, 1.0, 0.5),
        (3.0, 1.0, 1.5),
        (0.9, 1.0, 0.9),
        (1.0, 0.0, 1.0),
    ],
)
def test_correction_ratio_clamps_model_ratio(measured_m, model_m, expected):
    assert correction_ratio(measured_m, model_m) == expected


@pytest.mark.parametrize(
    ("measured_m", "model_m"),
    [
        (nan, 1.0),
        (1.0, nan),
        (inf, 1.0),
        (1.0, inf),
        (-0.1, 1.0),
        (1.0, -0.1),
    ],
)
def test_correction_ratio_is_neutral_for_invalid_inputs(measured_m, model_m):
    assert correction_ratio(measured_m, model_m) == 1.0


def test_apply_correction_scales_only_today_wave_and_swell_heights():
    today_hour = _hourly_conditions(datetime(2026, 7, 6, 9), wave=1.23, swell=0.87)
    tomorrow_hour = _hourly_conditions(datetime(2026, 7, 7, 9), wave=2.0, swell=1.5)
    hours = [today_hour, tomorrow_hour]

    corrected = apply_correction(hours, ratio=0.5, today=date(2026, 7, 6))

    assert corrected is not hours
    assert corrected[0] is not today_hour
    assert corrected[0].wave_height_m == 0.61
    assert corrected[0].swell_height_m == 0.43
    assert corrected[0].wave_period_s == today_hour.wave_period_s
    assert corrected[0].swell_period_s == today_hour.swell_period_s
    assert corrected[1] == tomorrow_hour


def _hourly_conditions(
    timestamp: datetime,
    *,
    wave: float,
    swell: float,
) -> HourlyConditions:
    return HourlyConditions(
        time=timestamp,
        wave_height_m=wave,
        wave_period_s=6.0,
        wave_direction_deg=300.0,
        swell_height_m=swell,
        swell_period_s=7.0,
        swell_direction_deg=310.0,
        wind_speed_bft=4,
        wind_direction_deg=90.0,
    )
