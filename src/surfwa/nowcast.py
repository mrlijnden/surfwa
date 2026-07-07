from __future__ import annotations

from dataclasses import replace
from datetime import date
from math import isfinite

from surfwa.fetch.openmeteo import HourlyConditions


def correction_ratio(measured_m: float, model_m: float) -> float:
    if (
        not isfinite(measured_m)
        or not isfinite(model_m)
        or measured_m < 0
        or model_m < 0
    ):
        return 1.0
    if model_m < 0.05:
        return 1.0
    return max(0.5, min(1.5, measured_m / model_m))


def apply_correction(
    hours: list[HourlyConditions],
    ratio: float,
    today: date,
) -> list[HourlyConditions]:
    return [
        replace(
            hour,
            wave_height_m=round(hour.wave_height_m * ratio, 2),
            swell_height_m=round(hour.swell_height_m * ratio, 2),
        )
        if hour.time.date() == today
        else hour
        for hour in hours
    ]
