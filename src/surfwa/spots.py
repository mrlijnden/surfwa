from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_TIDE_PREFS = {"any", "high", "mid", "low", "rising", "falling", "not_low"}


@dataclass(frozen=True)
class SpotConfig:
    slug: str
    name: str
    region: str
    lat: float
    lon: float
    tide_station: str
    wave_buoy: str
    coast_normal_deg: int
    tide_pref: str
    min_wave_m: float
    min_period_s: float
    swell_sector: tuple[int, int] | None = None
    favorite: bool = False
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_spots(path: Path) -> dict[str, SpotConfig]:
    raw = yaml.safe_load(path.read_text())
    spots: dict[str, SpotConfig] = {}
    for slug, d in raw.items():
        if d["tide_pref"] not in VALID_TIDE_PREFS:
            raise ValueError(f"{slug}: invalid tide_pref {d['tide_pref']!r}")
        sector = d.get("swell_sector")
        spots[slug] = SpotConfig(
            slug=slug,
            name=d["name"],
            region=d["region"],
            lat=float(d["lat"]),
            lon=float(d["lon"]),
            tide_station=d["tide_station"],
            wave_buoy=d["wave_buoy"],
            coast_normal_deg=int(d["coast_normal_deg"]),
            tide_pref=d["tide_pref"],
            min_wave_m=float(d["min_wave_m"]),
            min_period_s=float(d["min_period_s"]),
            swell_sector=tuple(sector) if sector else None,
            favorite=bool(d.get("favorite", False)),
            notes=list(d.get("notes", [])),
            warnings=list(d.get("warnings", [])),
        )
    return spots
