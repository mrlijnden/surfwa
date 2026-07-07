from pathlib import Path

from surfwa.spots import load_spots

SPOTS = Path(__file__).parent.parent / "knowledge" / "spots.yaml"


def test_loads_all_spots():
    spots = load_spots(SPOTS)
    assert len(spots) == 15
    ij = spots["ijmuiden"]
    assert ij.region == "NH"
    assert ij.swell_sector == (240, 325)
    assert ij.tide_pref == "falling"
    assert spots["scheveningen"].swell_sector is None
    assert spots["scheveningen"].warnings


def test_rejects_bad_tide_pref(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "x:\n  name: X\n  region: ZH\n  lat: 52.0\n  lon: 4.0\n"
        "  tide_station: s\n  wave_buoy: b\n  coast_normal_deg: 300\n"
        "  tide_pref: sideways\n  min_wave_m: 0.4\n  min_period_s: 5.0\n"
        "  notes: []\n  warnings: []\n"
    )
    import pytest

    with pytest.raises(ValueError, match="tide_pref"):
        load_spots(bad)
