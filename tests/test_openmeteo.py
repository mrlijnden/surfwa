from datetime import datetime
from urllib.parse import parse_qs, urlparse

import responses

from surfwa.fetch.openmeteo import MARINE_URL, WEATHER_URL, fetch_hourly, kmh_to_bft


def test_kmh_to_bft_thresholds():
    assert kmh_to_bft(0) == 0
    assert kmh_to_bft(10) == 2
    assert kmh_to_bft(35) == 5
    assert kmh_to_bft(200) == 12


@responses.activate
def test_fetch_hourly_merges_marine_and_weather_hourly_conditions():
    times = ["2026-07-06T00:00", "2026-07-06T01:00"]
    responses.add(
        responses.GET,
        MARINE_URL,
        json={
            "hourly": {
                "time": times,
                "wave_height": [1.2, 1.2],
                "wave_period": [6.0, 6.0],
                "wave_direction": [300, 300],
                "swell_wave_height": [0.8, 0.8],
                "swell_wave_period": [7.5, 7.5],
                "swell_wave_direction": [310, 310],
            }
        },
        status=200,
    )
    responses.add(
        responses.GET,
        WEATHER_URL,
        json={
            "hourly": {
                "time": times,
                "wind_speed_10m": [20.0, 20.0],
                "wind_direction_10m": [90, 90],
            }
        },
        status=200,
    )

    conditions = fetch_hourly(52.46, 4.56, days=2)

    assert len(conditions) == 2
    first = conditions[0]
    assert first.time == datetime(2026, 7, 6, 0, 0)
    assert first.time.tzinfo is None
    assert first.wave_height_m == 1.2
    assert first.wave_period_s == 6.0
    assert first.wave_direction_deg == 300
    assert first.swell_height_m == 0.8
    assert first.swell_period_s == 7.5
    assert first.swell_direction_deg == 310
    assert first.wind_speed_bft == 4
    assert first.wind_direction_deg == 90

    for call in responses.calls:
        params = parse_qs(urlparse(call.request.url).query)
        assert params["timezone"] == ["Europe/Amsterdam"]
        assert params["forecast_days"] == ["2"]


@responses.activate
def test_fetch_hourly_defaults_optional_swell_null_values_to_zero():
    times = ["2026-07-06T00:00"]
    responses.add(
        responses.GET,
        MARINE_URL,
        json={
            "hourly": {
                "time": times,
                "wave_height": [1.0],
                "wave_period": [6.0],
                "wave_direction": [300],
                "swell_wave_height": [None],
                "swell_wave_period": [None],
                "swell_wave_direction": [None],
            }
        },
    )
    responses.add(
        responses.GET,
        WEATHER_URL,
        json={
            "hourly": {
                "time": times,
                "wind_speed_10m": [0.0],
                "wind_direction_10m": [90],
            }
        },
    )

    first = fetch_hourly(52.46, 4.56, days=1)[0]

    assert first.swell_height_m == 0.0
    assert first.swell_period_s == 0.0
    assert first.swell_direction_deg == 0.0
    assert first.wind_speed_bft == 0
    assert first.wind_direction_deg == 90


@responses.activate
def test_fetch_hourly_joins_weather_by_timestamp():
    marine_times = ["2026-07-06T00:00", "2026-07-06T01:00"]
    weather_times = ["2026-07-06T01:00", "2026-07-06T00:00"]
    responses.add(
        responses.GET,
        MARINE_URL,
        json={
            "hourly": {
                "time": marine_times,
                "wave_height": [1.0, 1.0],
                "wave_period": [6.0, 6.0],
                "wave_direction": [300, 300],
                "swell_wave_height": [0.5, 0.5],
                "swell_wave_period": [7.0, 7.0],
                "swell_wave_direction": [300, 300],
            }
        },
    )
    responses.add(
        responses.GET,
        WEATHER_URL,
        json={
            "hourly": {
                "time": weather_times,
                "wind_speed_10m": [35.0, 20.0],
                "wind_direction_10m": [180, 90],
            }
        },
    )

    first = fetch_hourly(52.46, 4.56, days=1)[0]

    assert first.time == datetime(2026, 7, 6, 0, 0)
    assert first.wind_speed_bft == 4
    assert first.wind_direction_deg == 90


@responses.activate
def test_fetch_hourly_skips_hours_without_wind():
    times = ["2026-07-06T00:00"]
    responses.add(
        responses.GET,
        MARINE_URL,
        json={
            "hourly": {
                "time": times,
                "wave_height": [1.0],
                "wave_period": [6.0],
                "wave_direction": [300],
                "swell_wave_height": [0.5],
                "swell_wave_period": [7.0],
                "swell_wave_direction": [300],
            }
        },
    )
    responses.add(
        responses.GET,
        WEATHER_URL,
        json={
            "hourly": {
                "time": times,
                "wind_speed_10m": [None],
                "wind_direction_10m": [90],
            }
        },
    )

    assert fetch_hourly(52.46, 4.56, days=1) == []
