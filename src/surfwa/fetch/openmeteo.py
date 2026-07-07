from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

_BFT_THRESHOLDS = [2, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]


@dataclass(frozen=True)
class HourlyConditions:
    time: datetime
    wave_height_m: float
    wave_period_s: float
    wave_direction_deg: float
    swell_height_m: float
    swell_period_s: float
    swell_direction_deg: float
    wind_speed_bft: int
    wind_direction_deg: float


def kmh_to_bft(kmh: float) -> int:
    for bft, threshold in enumerate(_BFT_THRESHOLDS):
        if kmh < threshold:
            return bft
    return 12


def fetch_hourly(
    lat: float,
    lon: float,
    days: int = 3,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[HourlyConditions]:
    marine = requests.get(
        MARINE_URL,
        params={
            **_base_params(lat, lon, days, start_date, end_date),
            "hourly": ",".join(
                [
                    "wave_height",
                    "wave_period",
                    "wave_direction",
                    "swell_wave_height",
                    "swell_wave_period",
                    "swell_wave_direction",
                ]
            ),
        },
        timeout=30,
    )
    marine.raise_for_status()

    weather = requests.get(
        WEATHER_URL,
        params={
            **_base_params(lat, lon, days, start_date, end_date),
            "hourly": "wind_speed_10m,wind_direction_10m",
        },
        timeout=30,
    )
    weather.raise_for_status()

    marine_hourly = marine.json()["hourly"]
    weather_hourly = weather.json()["hourly"]
    weather_by_time = {
        timestamp: index for index, timestamp in enumerate(weather_hourly.get("time", []))
    }
    conditions: list[HourlyConditions] = []

    for index, timestamp in enumerate(marine_hourly.get("time", [])):
        weather_index = weather_by_time.get(timestamp)
        if weather_index is None:
            continue
        wave_height = _hourly_value(marine_hourly, "wave_height", index)
        wave_period = _hourly_value(marine_hourly, "wave_period", index)
        wave_direction = _hourly_value(marine_hourly, "wave_direction", index)
        wind_speed = _hourly_value(weather_hourly, "wind_speed_10m", weather_index)
        wind_direction = _hourly_value(weather_hourly, "wind_direction_10m", weather_index)
        if (
            wave_height is None
            or wave_period is None
            or wave_direction is None
            or wind_speed is None
            or wind_direction is None
        ):
            continue

        conditions.append(
            HourlyConditions(
                time=datetime.fromisoformat(timestamp),
                wave_height_m=float(wave_height),
                wave_period_s=float(wave_period),
                wave_direction_deg=float(wave_direction),
                swell_height_m=_number(marine_hourly, "swell_wave_height", index),
                swell_period_s=_number(marine_hourly, "swell_wave_period", index),
                swell_direction_deg=_number(marine_hourly, "swell_wave_direction", index),
                wind_speed_bft=kmh_to_bft(float(wind_speed)),
                wind_direction_deg=float(wind_direction),
            )
        )

    return conditions


def _base_params(
    lat: float,
    lon: float,
    days: int,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "Europe/Amsterdam",
    }
    if start_date is not None:
        params["start_date"] = start_date
        params["end_date"] = end_date or start_date
    else:
        params["forecast_days"] = days
    return params


def _hourly_value(hourly: dict[str, list[Any]], name: str, index: int) -> Any:
    values = hourly.get(name, [])
    if index >= len(values):
        return None
    return values[index]


def _number(hourly: dict[str, list[Any]], name: str, index: int) -> float:
    value = _hourly_value(hourly, name, index)
    return 0.0 if value is None else float(value)
