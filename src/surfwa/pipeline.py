from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from surfwa.fetch.openmeteo import HourlyConditions, fetch_hourly
from surfwa.fetch.rws import TideEvent, fetch_tide_curve, latest_buoy_hm0, tide_extremes
from surfwa.nowcast import apply_correction, correction_ratio
from surfwa.score import Window, find_windows, score_hours
from surfwa.spots import SpotConfig


@dataclass
class PipelineCapture:
    """Raw series the pipeline retains for chart rendering."""

    hours_by_spot: dict[str, list[HourlyConditions]] = field(default_factory=dict)
    tide_curve_by_station: dict[str, list[tuple[datetime, int]]] = field(
        default_factory=dict
    )
    extremes_by_station: dict[str, list[TideEvent]] = field(default_factory=dict)
    buoy_readings: dict[str, tuple[datetime, float]] = field(default_factory=dict)


def run_pipeline(
    spots: dict[str, SpotConfig],
    days: int = 3,
    start_date: str | None = None,
    end_date: str | None = None,
    spot_filter: str | None = None,
    use_nowcast: bool = True,
    capture: PipelineCapture | None = None,
) -> tuple[list[Window], list[str]]:
    windows: list[Window] = []
    problems: list[str] = []
    tide_cache: dict[str, list] = {}
    buoy_cache: dict[str, tuple | None] = {}

    if start_date:
        t_start = datetime.fromisoformat(start_date)
        t_end = datetime.fromisoformat(end_date or start_date) + timedelta(days=1)
    else:
        t_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        t_end = t_start + timedelta(days=days)

    for slug, spot in spots.items():
        if spot_filter and slug != spot_filter:
            continue

        try:
            hours = fetch_hourly(
                spot.lat,
                spot.lon,
                days=days,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            problems.append(f"{slug}: golfdata niet beschikbaar ({exc})")
            continue
        if not hours:
            problems.append(f"{slug}: golfdata leeg")
            continue

        if use_nowcast and not start_date and hours:
            if spot.wave_buoy not in buoy_cache:
                try:
                    buoy_cache[spot.wave_buoy] = latest_buoy_hm0(spot.wave_buoy)
                except Exception:
                    buoy_cache[spot.wave_buoy] = None
            reading = buoy_cache[spot.wave_buoy]
            if reading:
                now = datetime.now()
                current = min(hours, key=lambda h: abs(h.time - now))
                ratio = correction_ratio(reading[1], current.wave_height_m)
                hours = apply_correction(hours, ratio, date.today())
                if capture is not None:
                    capture.buoy_readings[spot.wave_buoy] = reading

        if capture is not None:
            capture.hours_by_spot[slug] = hours

        if spot.tide_station not in tide_cache:
            try:
                curve = fetch_tide_curve(spot.tide_station, t_start, t_end)
                if not curve:
                    problems.append(f"{slug}: getijdata leeg")
                tide_cache[spot.tide_station] = tide_extremes(curve)
                if capture is not None:
                    capture.tide_curve_by_station[spot.tide_station] = curve
                    capture.extremes_by_station[spot.tide_station] = tide_cache[
                        spot.tide_station
                    ]
            except Exception as exc:
                problems.append(f"{slug}: getijdata niet beschikbaar ({exc})")
                tide_cache[spot.tide_station] = []

        scored = score_hours(spot, hours, tide_cache[spot.tide_station])
        windows.extend(find_windows(spot, scored))

    return windows, problems
