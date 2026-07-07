import json
from datetime import datetime, timedelta

import responses

from surfwa.fetch.rws import (
    BASE,
    fetch_tide_curve,
    latest_buoy_hm0,
    tide_extremes,
)


OBS_URL = f"{BASE}/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
LATEST_URL = f"{BASE}/ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen"


def _rws_body(times_levels):
    return {
        "Succesvol": True,
        "WaarnemingenLijst": [
            {
                "MetingenLijst": [
                    {"Tijdstip": time, "Meetwaarde": {"Waarde_Numeriek": level}}
                    for time, level in times_levels
                ]
            }
        ],
    }


@responses.activate
def test_fetch_tide_curve_strips_timezone_for_mocked_values():
    responses.add(
        responses.POST,
        OBS_URL,
        json=_rws_body(
            [
                ("2026-07-06T10:00:00.000+02:00", 45),
                ("2026-07-06T10:10:00.000+02:00", 50),
            ]
        ),
    )

    curve = fetch_tide_curve(
        "scheveningen", datetime(2026, 7, 6), datetime(2026, 7, 7)
    )

    assert curve == [
        (datetime(2026, 7, 6, 10, 0), 45),
        (datetime(2026, 7, 6, 10, 10), 50),
    ]
    assert all(ts.tzinfo is None for ts, _ in curve)


@responses.activate
def test_fetch_tide_curve_uses_ddapi20_singular_request_shape():
    responses.add(responses.POST, OBS_URL, json=_rws_body([]))

    fetch_tide_curve("scheveningen", datetime(2026, 7, 6), datetime(2026, 7, 7))

    body = json.loads(responses.calls[0].request.body)
    assert body["Locatie"] == {"Code": "scheveningen"}
    assert body["AquoPlusWaarnemingMetadata"]["AquoMetadata"]["Grootheid"] == {
        "Code": "WATHTE"
    }
    assert "LocatieLijst" not in body
    assert "AquoPlusWaarnemingMetadataLijst" not in body
    assert body["ProcesType"] == "astronomisch"


@responses.activate
def test_fetch_tide_curve_uses_amsterdam_offset_for_winter_dates():
    responses.add(responses.POST, OBS_URL, json=_rws_body([]))

    fetch_tide_curve("scheveningen", datetime(2026, 1, 6), datetime(2026, 1, 7))

    body = json.loads(responses.calls[0].request.body)
    assert body["Periode"]["Begindatumtijd"] == "2026-01-06T00:00:00.000+01:00"
    assert body["Periode"]["Einddatumtijd"] == "2026-01-07T00:00:00.000+01:00"


def test_tide_extremes_finds_hw_and_lw():
    start = datetime(2026, 7, 6)
    levels = [0, 40, 70, 80, 70, 30, -20, -55, -68, -70, -60, -20, 30]
    curve = [(start + timedelta(hours=i), level) for i, level in enumerate(levels)]

    extremes = tide_extremes(curve)

    assert [event.kind for event in extremes] == ["HW", "LW"]
    assert extremes[0].time.hour == 3
    assert extremes[0].level_cm == 80
    assert extremes[1].time.hour == 9
    assert extremes[1].level_cm == -70


def test_tide_extremes_ignores_short_wiggles_on_high_resolution_curve():
    start = datetime(2026, 7, 6, 12)
    levels = [
        80,
        70,
        72,
        60,
        61,
        40,
        10,
        -20,
        -50,
        -70,
        -68,
        -45,
        -10,
        30,
        65,
        78,
    ]
    curve = [(start + timedelta(minutes=30 * i), level) for i, level in enumerate(levels)]

    extremes = tide_extremes(curve)

    assert [event.kind for event in extremes] == ["LW"]
    assert extremes[0].time == start + timedelta(hours=4, minutes=30)
    assert extremes[0].level_cm == -70


@responses.activate
def test_latest_buoy_hm0_returns_none_on_204():
    responses.add(responses.POST, LATEST_URL, status=204)

    assert latest_buoy_hm0("ijgeul.2.boei") is None


@responses.activate
def test_latest_buoy_hm0_converts_cm_to_m():
    responses.add(
        responses.POST,
        LATEST_URL,
        json=_rws_body([("2026-07-06T11:50:00.000+02:00", 130)]),
    )

    timestamp, hm0 = latest_buoy_hm0(
        "ijgeul.2.boei", now=datetime(2026, 7, 6, 12, 0)
    )

    assert timestamp == datetime(2026, 7, 6, 11, 50)
    assert hm0 == 1.3


@responses.activate
def test_latest_buoy_hm0_ignores_stale_values():
    responses.add(
        responses.POST,
        LATEST_URL,
        json=_rws_body([("2017-05-10T19:40:00.000+02:00", 67)]),
    )

    assert latest_buoy_hm0("ijgeul.2.boei", now=datetime(2026, 7, 6, 12, 0)) is None
