from datetime import datetime, timedelta

from surfwa.fetch.openmeteo import HourlyConditions
from surfwa.fetch.rws import TideEvent
from surfwa.score import (
    angle_diff,
    board_advice,
    deg_to_compass,
    find_windows,
    score_hours,
    swell_factor,
    tide_factor,
    tide_phase_at,
    wind_factor,
)
from surfwa.spots import SpotConfig


SPOT = SpotConfig(
    slug="test",
    name="Test",
    region="NH",
    lat=52.4,
    lon=4.5,
    tide_station="x",
    wave_buoy="y",
    coast_normal_deg=300,
    tide_pref="any",
    min_wave_m=0.4,
    min_period_s=5.0,
    warnings=["pas op stroming"],
)
PIER = SpotConfig(
    slug="pier",
    name="Pier",
    region="NH",
    lat=52.4,
    lon=4.5,
    tide_station="x",
    wave_buoy="y",
    coast_normal_deg=300,
    tide_pref="any",
    min_wave_m=0.4,
    min_period_s=5.0,
    swell_sector=(240, 310),
)


def _hour(t, h=1.0, p=6.5, wdir=300, bft=2, winddir=120):
    return HourlyConditions(
        time=t,
        wave_height_m=h,
        wave_period_s=p,
        wave_direction_deg=wdir,
        swell_height_m=h * 0.7,
        swell_period_s=p,
        swell_direction_deg=wdir,
        wind_speed_bft=bft,
        wind_direction_deg=winddir,
    )


def _spot_with_tide(tide_pref):
    return SpotConfig(
        slug=f"tide-{tide_pref}",
        name="Tide",
        region="ZH",
        lat=51.6,
        lon=3.5,
        tide_station="x",
        wave_buoy="y",
        coast_normal_deg=315,
        tide_pref=tide_pref,
        min_wave_m=0.4,
        min_period_s=5.0,
    )


def test_angle_diff_wraps():
    assert angle_diff(350, 10) == 20
    assert angle_diff(10, 350) == 20


def test_deg_to_compass_dutch():
    assert deg_to_compass(0) == "N"
    assert deg_to_compass(225) == "ZW"
    assert deg_to_compass(292.5) == "WNW"


def test_wind_factor_offshore_beats_onshore_and_light_wind_is_fine():
    off = wind_factor(SPOT, 4, 120)
    on = wind_factor(SPOT, 4, 300)
    assert off == 1.0
    assert on < 0.5
    assert wind_factor(SPOT, 0, 300) == 1.0


def test_swell_factor_zero_below_minimums():
    t = datetime(2026, 7, 6, 12)
    assert swell_factor(SPOT, _hour(t, h=0.2)) == 0.0
    assert swell_factor(SPOT, _hour(t, p=3.0)) == 0.0
    assert swell_factor(SPOT, _hour(t)) > 0.5


def test_pier_blocks_northern_swell():
    t = datetime(2026, 7, 6, 12)
    assert swell_factor(PIER, _hour(t, wdir=350)) < swell_factor(
        PIER, _hour(t, wdir=280)
    )


def test_tide_phase():
    assert tide_phase_at(datetime(2026, 7, 6, 7), []) == "unknown"
    ex = [
        TideEvent(datetime(2026, 7, 6, 4), "LW", -60),
        TideEvent(datetime(2026, 7, 6, 10), "HW", 80),
        TideEvent(datetime(2026, 7, 6, 16), "LW", -60),
    ]
    assert tide_phase_at(datetime(2026, 7, 6, 10, 30), ex) == "high"
    assert tide_phase_at(datetime(2026, 7, 6, 7), ex) == "rising"
    assert tide_phase_at(datetime(2026, 7, 6, 13), ex) == "falling"
    assert tide_phase_at(datetime(2026, 7, 6, 16, 30), ex) == "low"


def test_tide_factor_not_low():
    spot = _spot_with_tide("not_low")
    assert tide_factor(spot, "low") < 0.5
    assert tide_factor(spot, "high") == 1.0


def test_tide_factor_supports_any_mid_and_exact_preferences():
    assert tide_factor(_spot_with_tide("any"), "low") == 1.0
    assert tide_factor(_spot_with_tide("any"), "unknown") == 1.0
    assert tide_factor(_spot_with_tide("not_low"), "unknown") == 0.7
    assert tide_factor(_spot_with_tide("mid"), "rising") == 1.0
    assert tide_factor(_spot_with_tide("mid"), "unknown") == 0.7
    assert tide_factor(_spot_with_tide("mid"), "high") < 1.0

    high_pref = _spot_with_tide("high")
    assert tide_factor(high_pref, "high") == 1.0
    assert tide_factor(high_pref, "unknown") == 0.7
    assert 0.5 < tide_factor(high_pref, "rising") < 1.0
    assert tide_factor(high_pref, "low") < tide_factor(high_pref, "rising")


def test_board_advice():
    assert board_advice(0.3, 6) == "longboard"
    assert board_advice(0.7, 6) == "fish/longboard"
    assert board_advice(1.2, 6) == "shortboard"
    assert board_advice(1.2, 9) == "shortboard/fish"


def test_windows_from_scored_hours():
    t0 = datetime(2026, 7, 6, 6)
    ex = [
        TideEvent(datetime(2026, 7, 6, 4), "LW", -60),
        TideEvent(datetime(2026, 7, 6, 10), "HW", 80),
        TideEvent(datetime(2026, 7, 6, 16), "LW", -60),
        TideEvent(datetime(2026, 7, 6, 22), "HW", 80),
    ]
    hours = [_hour(t0 + timedelta(hours=i)) for i in range(6)] + [
        _hour(t0 + timedelta(hours=6 + i), bft=6, winddir=300) for i in range(6)
    ]

    scored = score_hours(SPOT, hours, ex)
    windows = find_windows(SPOT, scored)

    assert all(0.0 <= hour.score <= 10.0 for hour in scored)
    assert len(windows) == 1
    w = windows[0]
    assert w.start == t0
    assert w.end == t0 + timedelta(hours=6)
    assert w.avg_height_m == 1.0
    assert w.avg_period_s == 6.5
    assert w.wind_desc == "OZO 2bft"
    assert w.tide_desc in {"high", "rising"}
    assert w.board == "shortboard"
    assert w.warnings == ["pas op stroming"]


def test_windows_report_sector_adjusted_height_for_blocked_swell():
    t0 = datetime(2026, 7, 6, 6)
    ex = [
        TideEvent(datetime(2026, 7, 6, 4), "LW", -60),
        TideEvent(datetime(2026, 7, 6, 10), "HW", 80),
    ]
    hours = [_hour(t0 + timedelta(hours=i), h=1.5, p=8, wdir=350) for i in range(2)]

    windows = find_windows(PIER, score_hours(PIER, hours, ex), min_score=2.0)

    assert len(windows) == 1
    assert windows[0].avg_height_m == 0.4
    assert windows[0].board == "longboard"
