from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from surfwa.fetch.openmeteo import HourlyConditions
from surfwa.fetch.rws import TideEvent
from surfwa.pipeline import PipelineCapture
from surfwa.score import Window, angle_diff
from surfwa.spots import SpotConfig

_DAY_NAMES = ["ma", "di", "wo", "do", "vr", "za", "zo"]
_MONTH_NAMES = [
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]
_WIND_COLORS = {"offshore": "#2a9d3f", "cross": "#e0a020", "onshore": "#d04030"}


class ChartUnavailableError(RuntimeError):
    pass


def stars(peak_score: float) -> str:
    return "★" * max(1, min(5, round(peak_score / 2)))


@dataclass(frozen=True)
class DayData:
    day: date
    best_spot: str
    coast_normal_deg: int
    hours: list[HourlyConditions]
    tide_curve: list[tuple[datetime, int]]
    extremes: list[TideEvent]
    windows: list[Window]
    nowcast_note: str | None


def assemble_days(
    capture: PipelineCapture,
    windows: list[Window],
    spots: dict[str, SpotConfig],
) -> list[DayData]:
    all_days = sorted(
        {h.time.date() for hours in capture.hours_by_spot.values() for h in hours}
    )
    days: list[DayData] = []
    for index, day in enumerate(all_days):
        day_windows = sorted(
            (w for w in windows if w.start.date() == day), key=lambda w: w.start
        )
        if day_windows:
            best = max(day_windows, key=lambda w: w.peak_score).spot_slug
        else:
            best = min(
                slug
                for slug, hours in capture.hours_by_spot.items()
                if any(h.time.date() == day for h in hours)
            )
        spot = spots[best]

        note = None
        if index == 0:
            reading = capture.buoy_readings.get(spot.wave_buoy)
            if reading:
                note = f"{spot.wave_buoy} nu: {reading[1]:.1f}m"

        days.append(
            DayData(
                day=day,
                best_spot=best,
                coast_normal_deg=spot.coast_normal_deg,
                hours=[
                    h
                    for h in capture.hours_by_spot.get(best, [])
                    if h.time.date() == day
                ],
                tide_curve=[
                    point
                    for point in capture.tide_curve_by_station.get(
                        spot.tide_station, []
                    )
                    if point[0].date() == day
                ],
                extremes=[
                    e
                    for e in capture.extremes_by_station.get(spot.tide_station, [])
                    if e.time.date() == day
                ],
                windows=day_windows,
                nowcast_note=note,
            )
        )
    return days


def render_chart(
    days: list[DayData],
    spots: dict[str, SpotConfig],
    out_path: Path,
) -> Path:
    plt = _pyplot()
    fig = build_figure(days, spots)
    out_path = Path(out_path)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def build_figure(days: list[DayData], spots: dict[str, SpotConfig]):
    plt = _pyplot()

    window_rows = [max(len(d.windows), 1) for d in days]
    fig = plt.figure(figsize=(11, sum(5.2 + 0.35 * rows for rows in window_rows)))
    gs = fig.add_gridspec(
        4 * len(days),
        1,
        height_ratios=[
            ratio for rows in window_rows for ratio in (3, 1, 2, 1 + 0.6 * rows)
        ],
        hspace=0.75,
    )

    for i, day in enumerate(days):
        ax_wave = fig.add_subplot(gs[4 * i])
        ax_wind = fig.add_subplot(gs[4 * i + 1], sharex=ax_wave)
        ax_tide = fig.add_subplot(gs[4 * i + 2], sharex=ax_wave)
        ax_win = fig.add_subplot(gs[4 * i + 3], sharex=ax_wave)
        for ax in (ax_wave, ax_wind, ax_tide, ax_win):
            ax.set_xlim(0, 24)
            ax.set_xticks(range(0, 25, 3))
        _wave_panel(ax_wave, day)
        _wind_panel(ax_wind, day)
        _tide_panel(ax_tide, day)
        _window_panel(ax_win, day, spots)
    return fig


def _pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ChartUnavailableError(
            "matplotlib is niet geïnstalleerd; installeer met: uv sync --extra image"
        ) from exc
    return plt


def _hour_of(t: datetime) -> float:
    return t.hour + t.minute / 60


def _day_label(day: date) -> str:
    return f"{_DAY_NAMES[day.weekday()]} {day.day} {_MONTH_NAMES[day.month - 1]}"


def _wave_panel(ax, day: DayData) -> None:
    title = f"surfwa — {_day_label(day.day)}"
    if day.nowcast_note:
        title += f"   ({day.nowcast_note})"
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.set_ylabel("golf (m)")
    if not day.hours:
        ax.text(12, 0.5, "geen data", ha="center", va="center", color="gray")
        return

    xs = [_hour_of(h.time) for h in day.hours]
    ys = [h.wave_height_m for h in day.hours]
    ax.fill_between(xs, ys, color="#4a90c4", alpha=0.5)
    ax.plot(xs, ys, color="#2a6b9c", linewidth=1.2)
    ax.set_ylim(0, max(max(ys) * 1.3, 1.0))
    peak = max(day.hours, key=lambda h: h.wave_height_m)
    ax.annotate(
        f"{peak.wave_period_s:.0f}s",
        (_hour_of(peak.time), peak.wave_height_m),
        textcoords="offset points",
        xytext=(0, 4),
        ha="center",
        fontsize=8,
    )


def _wind_panel(ax, day: DayData) -> None:
    ax.set_ylabel("wind")
    ax.set_ylim(-1, 1)
    ax.set_yticks([])
    if not day.hours:
        ax.text(12, 0, "geen data", ha="center", va="center", color="gray")
        return

    offshore_deg = (day.coast_normal_deg + 180) % 360
    for h in day.hours:
        diff = angle_diff(h.wind_direction_deg, offshore_deg)
        kind = "offshore" if diff <= 45 else "cross" if diff <= 105 else "onshore"
        # arrow points where the wind blows to
        to_rad = math.radians((h.wind_direction_deg + 180) % 360)
        ax.annotate(
            "",
            xy=(_hour_of(h.time) + 0.4 * math.sin(to_rad), 0.5 * math.cos(to_rad)),
            xytext=(_hour_of(h.time), 0),
            arrowprops={"arrowstyle": "-|>", "color": _WIND_COLORS[kind]},
        )
    for h in day.hours:
        if h.time.hour % 3 == 0:
            ax.text(
                _hour_of(h.time),
                -0.85,
                f"{h.wind_speed_bft}",
                ha="center",
                fontsize=7,
                color="gray",
            )


def _tide_panel(ax, day: DayData) -> None:
    ax.set_ylabel("getij (cm)")
    if not day.tide_curve:
        ax.text(12, 0, "geen data", ha="center", va="center", color="gray")
        ax.set_ylim(-1, 1)
        ax.set_yticks([])
        return

    xs = [_hour_of(t) for t, _ in day.tide_curve]
    ys = [level for _, level in day.tide_curve]
    ax.plot(xs, ys, color="#3a7a5c", linewidth=1.2)
    for event in day.extremes:
        ax.annotate(
            f"{event.kind} {event.time:%H:%M}",
            (_hour_of(event.time), event.level_cm),
            textcoords="offset points",
            xytext=(0, 5 if event.kind == "HW" else -12),
            ha="center",
            fontsize=8,
        )


def _window_panel(ax, day: DayData, spots: dict[str, SpotConfig]) -> None:
    ax.set_xlabel("uur")
    ax.set_yticks([])
    if not day.windows:
        ax.set_ylim(0, 1)
        ax.text(12, 0.5, "geen surf", ha="center", va="center", color="gray")
        return

    ax.set_ylim(0, len(day.windows))
    for row, window in enumerate(reversed(day.windows)):
        start = _hour_of(window.start)
        end = 24.0 if window.end.date() > day.day else _hour_of(window.end)
        spot = spots[window.spot_slug]
        ax.broken_barh([(start, end - start)], (row + 0.15, 0.7), color="#4a90c4")
        label = (
            f"{spot.name}  {window.start.hour}-{window.end.hour}u"
            f"  {stars(window.peak_score)}  [{window.board}]"
        )
        if window.warnings:
            label += f"  ! {window.warnings[0]}"
        ax.text(
            0.3,
            row + 0.5,
            label,
            va="center",
            fontsize=8.5,
            bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none", "pad": 1},
        )
