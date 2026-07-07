from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


BASE = "https://ddapi20-waterwebservices.rijkswaterstaat.nl"

_AMSTERDAM = ZoneInfo("Europe/Amsterdam")
_OBS_PATH = "/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
_LATEST_PATH = "/ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen"
_EXTREME_WINDOW = timedelta(hours=3)
_MAX_BUOY_AGE = timedelta(hours=12)


@dataclass(frozen=True)
class TideEvent:
    time: datetime
    kind: str
    level_cm: int


def _local(ts: str) -> datetime:
    return datetime.fromisoformat(ts).astimezone(_AMSTERDAM).replace(tzinfo=None)


def _post(path: str, body: dict) -> dict | None:
    response = requests.post(f"{BASE}{path}", json=body, timeout=30)
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return response.json()


def fetch_tide_curve(
    station: str, start: datetime, end: datetime
) -> list[tuple[datetime, int]]:
    body = {
        "AquoPlusWaarnemingMetadata": {
            "AquoMetadata": {"Grootheid": {"Code": "WATHTE"}}
        },
        "Locatie": {"Code": station},
        "Periode": {
            "Begindatumtijd": _format_period_time(start),
            "Einddatumtijd": _format_period_time(end),
        },
        "ProcesType": "astronomisch",
    }
    data = _post(_OBS_PATH, body)
    if not data or not data.get("Succesvol"):
        return []

    points: list[tuple[datetime, int]] = []
    for measurement in _measurements(data):
        value = measurement.get("Meetwaarde", {}).get("Waarde_Numeriek")
        if value is None or value > 9000:
            continue
        timestamp = measurement.get("Tijdstip")
        if not timestamp:
            continue
        points.append((_local(timestamp), int(value)))
    return sorted(points)


def tide_extremes(curve: list[tuple[datetime, int]]) -> list[TideEvent]:
    events: list[TideEvent] = []
    for index in range(1, len(curve) - 1):
        time, level = curve[index]
        window = [
            value
            for timestamp, value in curve
            if abs(timestamp - time) <= _EXTREME_WINDOW
        ]
        if not window:
            continue

        if level == max(window) and level > min(window):
            events.append(TideEvent(time, "HW", level))
        elif level == min(window) and level < max(window):
            events.append(TideEvent(time, "LW", level))

    deduped: list[TideEvent] = []
    for event in events:
        if (
            deduped
            and deduped[-1].kind == event.kind
            and event.time - deduped[-1].time < _EXTREME_WINDOW
        ):
            if (
                event.kind == "HW"
                and event.level_cm > deduped[-1].level_cm
                or event.kind == "LW"
                and event.level_cm < deduped[-1].level_cm
            ):
                deduped[-1] = event
            continue
        deduped.append(event)
    return deduped


def latest_buoy_hm0(
    buoy: str,
    now: datetime | None = None,
    max_age: timedelta = _MAX_BUOY_AGE,
) -> tuple[datetime, float] | None:
    body = {
        "AquoPlusWaarnemingMetadataLijst": [
            {"AquoMetadata": {"Grootheid": {"Code": "Hm0"}}}
        ],
        "LocatieLijst": [{"Code": buoy}],
        "ProcesType": "meting",
    }
    data = _post(_LATEST_PATH, body)
    if not data or not data.get("Succesvol"):
        return None

    measurements = list(_measurements(data))
    if not measurements:
        return None

    measurement = measurements[-1]
    value = measurement.get("Meetwaarde", {}).get("Waarde_Numeriek")
    timestamp = measurement.get("Tijdstip")
    if value is None or value > 9000 or not timestamp:
        return None
    measured_at = _local(timestamp)
    reference = now or datetime.now()
    if reference - measured_at > max_age:
        return None
    return measured_at, value / 100.0


def _format_period_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=_AMSTERDAM)
    else:
        value = value.astimezone(_AMSTERDAM)
    return value.isoformat(timespec="milliseconds")


def _measurements(data: dict):
    for observation in data.get("WaarnemingenLijst") or []:
        yield from observation.get("MetingenLijst") or []
