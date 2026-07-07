from __future__ import annotations

import requests

FEED_URL = "https://data.buienradar.nl/2.0/feed/json"
COASTAL = ("IJmuiden", "Hoek van Holland")


def coastal_wind() -> dict[str, tuple[int, str]]:
    response = requests.get(FEED_URL, timeout=30)
    response.raise_for_status()

    wind: dict[str, tuple[int, str]] = {}
    measurements = response.json().get("actual", {}).get("stationmeasurements", [])
    for measurement in measurements:
        station = measurement.get("stationname", "").removeprefix("Meetstation ")
        windspeed = measurement.get("windspeedBft")
        if station in COASTAL and windspeed is not None:
            wind[station] = (windspeed, measurement.get("winddirection") or "?")
    return wind
