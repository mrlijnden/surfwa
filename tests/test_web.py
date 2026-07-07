from datetime import date, datetime, timedelta
from unittest.mock import patch

from surfwa.score import Window
from surfwa.spots import SpotConfig

SPOTS = {
    slug: SpotConfig(
        slug=slug,
        name=name,
        region=region,
        lat=52.4,
        lon=4.5,
        tide_station="x",
        wave_buoy="y",
        coast_normal_deg=300,
        tide_pref="any",
        min_wave_m=0.4,
        min_period_s=5.0,
    )
    for slug, name, region in [
        ("aspot", "Aspot", "NH"),
        ("bspot", "Bspot", "NH"),
        ("cspot", "Cspot", "ZH"),
        ("dspot", "Dspot", "ZH"),
    ]
}

DAY1 = date(2026, 7, 7)
DAY2 = date(2026, 7, 8)


def _window(slug: str, day: date, start_h: int, end_h: int, peak: float) -> Window:
    t0 = datetime(day.year, day.month, day.day)
    return Window(
        spot_slug=slug,
        start=t0 + timedelta(hours=start_h),
        end=t0 + timedelta(hours=end_h),
        peak_score=peak,
        avg_height_m=1.2,
        avg_period_s=5.4,
        wind_desc="NNW 2bft",
        tide_desc="falling",
        board="shortboard",
        warnings=["Open spot: wordt snel hotseklots"],
    )


def test_digest_keeps_top3_per_day_one_per_spot():
    from surfwa.render.web import digest

    windows = [
        _window("aspot", DAY1, 18, 23, 7.5),
        _window("aspot", DAY1, 4, 6, 6.0),
        _window("bspot", DAY1, 12, 14, 5.0),
        _window("cspot", DAY1, 1, 3, 4.5),
        _window("dspot", DAY1, 2, 3, 4.2),
        _window("bspot", DAY2, 9, 12, 6.2),
    ]

    result = digest(windows)

    assert [day for day, _ in result] == [DAY1, DAY2]
    day1 = result[0][1]
    assert [w.spot_slug for w in day1] == ["aspot", "bspot", "cspot"]
    assert day1[0].peak_score == 7.5
    assert [w.spot_slug for w in result[1][1]] == ["bspot"]


def test_digest_appends_favorites_best_window_below_top3():
    from surfwa.render.web import digest

    windows = [
        _window("aspot", DAY1, 18, 23, 7.5),
        _window("bspot", DAY1, 12, 14, 5.0),
        _window("cspot", DAY1, 1, 3, 4.5),
        _window("dspot", DAY1, 21, 23, 4.2),
        _window("dspot", DAY1, 2, 3, 3.1),
        _window("bspot", DAY2, 9, 12, 6.2),
    ]

    result = digest(windows, favorites={"dspot"})

    day1 = result[0][1]
    assert [w.spot_slug for w in day1] == ["aspot", "bspot", "cspot", "dspot"]
    assert day1[3].peak_score == 4.2
    # dspot has no window on DAY2: stays silent
    assert [w.spot_slug for w in result[1][1]] == ["bspot"]


def test_digest_does_not_duplicate_favorite_already_in_top3():
    from surfwa.render.web import digest

    windows = [
        _window("dspot", DAY1, 18, 23, 7.5),
        _window("bspot", DAY1, 12, 14, 5.0),
    ]

    result = digest(windows, favorites={"dspot"})

    assert [w.spot_slug for w in result[0][1]] == ["dspot", "bspot"]


def test_render_html_marks_favorite_rows():
    from surfwa.render.web import digest, render_html

    spots = dict(SPOTS)
    spots["dspot"] = SPOTS["dspot"].__class__(
        **{**SPOTS["dspot"].__dict__, "favorite": True}
    )
    windows = [_window("dspot", DAY1, 21, 23, 4.2)]

    html = render_html(
        digest(windows, favorites={"dspot"}),
        spots,
        live=None,
        problems=[],
        generated=datetime(2026, 7, 7, 6, 30),
        chart_file=None,
    )

    assert "Dspot ♥" in html


def test_render_html_shows_digest_live_wind_and_chart():
    from surfwa.render.web import digest, render_html

    windows = [_window("aspot", DAY1, 18, 24, 7.5)]
    html = render_html(
        digest(windows),
        SPOTS,
        live={"IJmuiden": (5, "WNW")},
        problems=[],
        generated=datetime(2026, 7, 7, 6, 30),
        chart_file="chart.png",
    )

    assert html.startswith("<!doctype html>")
    assert "Aspot" in html
    assert "18-0u" in html
    assert "★" in html
    assert "1.2m @ 5.4s" in html
    assert "IJmuiden WNW 5bft" in html
    assert '<img src="chart.png"' in html
    assert "prefers-color-scheme" in html
    assert "07-07-2026 06:30" in html


def test_render_html_without_chart_or_windows():
    from surfwa.render.web import render_html

    html = render_html(
        [],
        SPOTS,
        live=None,
        problems=["aspot: golfdata niet beschikbaar (down)"],
        generated=datetime(2026, 7, 7, 6, 30),
        chart_file=None,
    )

    assert "<img" not in html
    assert "geen surf" in html
    assert "golfdata niet beschikbaar" in html


def test_build_site_writes_index_and_chart(tmp_path):
    from surfwa.render.web import build_site

    windows = [_window("aspot", DAY1, 18, 24, 7.5)]

    def fake_chart(days, spots, out):
        out.write_bytes(b"png")
        return out

    with (
        patch("surfwa.render.web.run_pipeline", return_value=(windows, [])),
        patch("surfwa.render.web.coastal_wind", return_value={"IJmuiden": (5, "WNW")}),
        patch("surfwa.render.web.assemble_days", return_value=[]),
        patch("surfwa.render.web.render_chart", side_effect=fake_chart),
    ):
        index = build_site(SPOTS, days=3, out_dir=tmp_path / "site")

    assert index == tmp_path / "site" / "index.html"
    assert index.exists()
    assert (tmp_path / "site" / "chart.png").exists()
    assert "Aspot" in index.read_text()


def test_build_site_degrades_without_matplotlib(tmp_path):
    from surfwa.render.chart import ChartUnavailableError
    from surfwa.render.web import build_site

    def unavailable(days, spots, out):
        raise ChartUnavailableError("matplotlib ontbreekt")

    with (
        patch("surfwa.render.web.run_pipeline", return_value=([], [])),
        patch("surfwa.render.web.coastal_wind", side_effect=RuntimeError("down")),
        patch("surfwa.render.web.assemble_days", return_value=[]),
        patch("surfwa.render.web.render_chart", side_effect=unavailable),
    ):
        index = build_site(SPOTS, days=3, out_dir=tmp_path / "site")

    html = index.read_text()
    assert "<img" not in html
    assert "actuele wind niet beschikbaar" in html
