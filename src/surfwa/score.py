from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from surfwa.fetch.openmeteo import HourlyConditions
from surfwa.fetch.rws import TideEvent
from surfwa.spots import SpotConfig


_COMPASS = [
    "N",
    "NNO",
    "NO",
    "ONO",
    "O",
    "OZO",
    "ZO",
    "ZZO",
    "Z",
    "ZZW",
    "ZW",
    "WZW",
    "W",
    "WNW",
    "NW",
    "NNW",
]
_TIDE_EVENT_WINDOW = timedelta(hours=1, minutes=30)


@dataclass(frozen=True)
class HourScore:
    time: datetime
    score: float
    wind_factor: float
    swell_factor: float
    tide_factor: float
    tide_phase: str
    conditions: HourlyConditions


@dataclass(frozen=True)
class Window:
    spot_slug: str
    start: datetime
    end: datetime
    peak_score: float
    avg_height_m: float
    avg_period_s: float
    wind_desc: str
    tide_desc: str
    board: str
    warnings: list[str]


def angle_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return 360 - diff if diff > 180 else diff


def deg_to_compass(deg: float) -> str:
    return _COMPASS[int((deg % 360) / 22.5 + 0.5) % len(_COMPASS)]


def wind_factor(spot: SpotConfig, bft: int, wind_dir_deg: float) -> float:
    if bft <= 1:
        return 1.0

    offshore_deg = (spot.coast_normal_deg + 180) % 360
    offshore_diff = angle_diff(wind_dir_deg, offshore_deg)
    if offshore_diff <= 45:
        if bft <= 4:
            return 1.0
        if bft <= 6:
            return 0.7
        return 0.4

    if offshore_diff <= 105:
        return {2: 0.9, 3: 0.8, 4: 0.6, 5: 0.4, 6: 0.3}.get(bft, 0.1)

    return {2: 0.8, 3: 0.5, 4: 0.3, 5: 0.15}.get(bft, 0.05)


def swell_factor(spot: SpotConfig, conditions: HourlyConditions) -> float:
    height = surfable_height_m(spot, conditions)
    period = conditions.wave_period_s

    if height < spot.min_wave_m or period < spot.min_period_s:
        return 0.0

    size_quality = min(height / 1.0, 1.0)
    period_quality = min(period / 7.0, 1.0)
    return size_quality * (0.5 + 0.5 * period_quality)


def surfable_height_m(spot: SpotConfig, conditions: HourlyConditions) -> float:
    height = conditions.wave_height_m
    period = conditions.wave_period_s
    direction = conditions.wave_direction_deg

    if spot.swell_sector is not None and not _direction_in_sector(
        direction, spot.swell_sector
    ):
        height *= 0.3
    return height


def tide_phase_at(t: datetime, extremes: list[TideEvent]) -> str:
    if not extremes:
        return "unknown"

    ordered = sorted(extremes, key=lambda event: event.time)
    nearest = min(ordered, key=lambda event: abs(event.time - t))
    if abs(nearest.time - t) <= _TIDE_EVENT_WINDOW:
        return "high" if nearest.kind == "HW" else "low"

    next_event = next((event for event in ordered if event.time > t), None)
    if next_event is not None:
        return "rising" if next_event.kind == "HW" else "falling"

    return "falling" if nearest.kind == "HW" else "rising"


def tide_factor(spot: SpotConfig, phase: str) -> float:
    pref = spot.tide_pref
    if pref == "any":
        return 1.0
    if phase == "unknown":
        return 0.7
    if pref == "not_low":
        return 0.2 if phase == "low" else 1.0
    if pref == "mid":
        return 1.0 if phase in {"rising", "falling"} else 0.6
    if phase == pref:
        return 1.0

    adjacent = {
        "high": {"rising", "falling"},
        "low": {"rising", "falling"},
        "rising": {"high", "low"},
        "falling": {"high", "low"},
    }
    return 0.7 if phase in adjacent.get(pref, set()) else 0.4


def board_advice(height_m: float, period_s: float) -> str:
    if height_m < 0.5:
        return "longboard"
    if height_m < 0.9:
        return "fish/longboard"
    return "shortboard" if period_s < 8 else "shortboard/fish"


def score_hours(
    spot: SpotConfig,
    hours: list[HourlyConditions],
    extremes: list[TideEvent],
) -> list[HourScore]:
    scored: list[HourScore] = []
    for conditions in hours:
        wind = wind_factor(
            spot, conditions.wind_speed_bft, conditions.wind_direction_deg
        )
        swell = swell_factor(spot, conditions)
        phase = tide_phase_at(conditions.time, extremes)
        tide = tide_factor(spot, phase)
        scored.append(
            HourScore(
                time=conditions.time,
                score=round(10 * wind * swell * tide, 1),
                wind_factor=wind,
                swell_factor=swell,
                tide_factor=tide,
                tide_phase=phase,
                conditions=conditions,
            )
        )
    return scored


def find_windows(
    spot: SpotConfig,
    scored: list[HourScore],
    min_score: float = 4.0,
) -> list[Window]:
    windows: list[Window] = []
    run: list[HourScore] = []

    def flush() -> None:
        if not run:
            return

        heights = [surfable_height_m(spot, hour.conditions) for hour in run]
        periods = [hour.conditions.wave_period_s for hour in run]
        avg_height = sum(heights) / len(heights)
        avg_period = sum(periods) / len(periods)
        peak = max(run, key=lambda hour: hour.score)
        conditions = peak.conditions
        windows.append(
            Window(
                spot_slug=spot.slug,
                start=run[0].time,
                end=run[-1].time + timedelta(hours=1),
                peak_score=peak.score,
                avg_height_m=round(avg_height, 1),
                avg_period_s=round(avg_period, 1),
                wind_desc=(
                    f"{deg_to_compass(conditions.wind_direction_deg)} "
                    f"{conditions.wind_speed_bft}bft"
                ),
                tide_desc=peak.tide_phase,
                board=board_advice(avg_height, avg_period),
                warnings=list(spot.warnings),
            )
        )
        run.clear()

    for hour in scored:
        if hour.score >= min_score and (
            not run or hour.time - run[-1].time == timedelta(hours=1)
        ):
            run.append(hour)
            continue

        flush()
        if hour.score >= min_score:
            run.append(hour)

    flush()
    return windows


def _direction_in_sector(direction: float, sector: tuple[int, int]) -> bool:
    low, high = sector
    direction %= 360
    low %= 360
    high %= 360
    if low <= high:
        return low <= direction <= high
    return direction >= low or direction <= high
