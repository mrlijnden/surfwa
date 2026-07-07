from datetime import datetime
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

import pytest

from surfwa.render.prose import (
    CodexUnavailable,
    build_prompt,
    generate_prose,
    generate_update,
    validate_prose,
)
from surfwa.score import Window


W = Window(
    spot_slug="scheveningen",
    start=datetime(2026, 7, 7, 15),
    end=datetime(2026, 7, 7, 18),
    peak_score=6.5,
    avg_height_m=0.9,
    avg_period_s=6.0,
    wind_desc="ZW 3bft",
    tide_desc="rising",
    board="fish/longboard",
    warnings=[],
)

MORNING_WINDOW = Window(
    spot_slug="wijk-aan-zee",
    start=datetime(2026, 7, 7, 7),
    end=datetime(2026, 7, 7, 10),
    peak_score=5.4,
    avg_height_m=0.7,
    avg_period_s=6.0,
    wind_desc="ZW 2bft",
    tide_desc="rising",
    board="fish/longboard",
    warnings=[],
)

WIJK_AFTERNOON_WINDOW = Window(
    spot_slug="wijk-aan-zee",
    start=datetime(2026, 7, 7, 15),
    end=datetime(2026, 7, 7, 18),
    peak_score=5.4,
    avg_height_m=0.7,
    avg_period_s=6.0,
    wind_desc="ZW 2bft",
    tide_desc="rising",
    board="fish/longboard",
    warnings=[],
)

CASTRICUM_AFTERNOON_WINDOW = Window(
    spot_slug="castricum",
    start=datetime(2026, 7, 7, 15),
    end=datetime(2026, 7, 7, 18),
    peak_score=5.4,
    avg_height_m=0.7,
    avg_period_s=6.0,
    wind_desc="ZW 2bft",
    tide_desc="rising",
    board="fish/longboard",
    warnings=[],
)

NOORDWIJK_WINDOW = Window(
    spot_slug="noordwijk",
    start=datetime(2026, 7, 7, 7),
    end=datetime(2026, 7, 7, 10),
    peak_score=5.4,
    avg_height_m=0.7,
    avg_period_s=6.0,
    wind_desc="ZW 2bft",
    tide_desc="rising",
    board="fish/longboard",
    warnings=[],
)

IJMUIDEN_LATE_WINDOW = Window(
    spot_slug="ijmuiden",
    start=datetime(2026, 7, 7, 23),
    end=datetime(2026, 7, 8, 1),
    peak_score=6.3,
    avg_height_m=0.8,
    avg_period_s=5.3,
    wind_desc="W 2bft",
    tide_desc="falling",
    board="fish/longboard",
    warnings=[],
)


def test_build_prompt_uses_fixed_style_guide_without_local_examples():
    prompt = build_prompt(
        '[{"spot": "scheveningen"}]',
        ["LOCAL EXAMPLE THAT SHOULD NOT BE SENT"],
    )

    assert "scheveningen" in prompt
    assert "LOCAL EXAMPLE THAT SHOULD NOT BE SENT" not in prompt
    assert "telegramstijl" in prompt
    assert "Verzin geen" in prompt


def test_generate_prose_runs_codex_exec_and_returns_stripped_stdout():
    with patch(
        "surfwa.render.prose.subprocess.run",
        return_value=CompletedProcess(
            args=["codex", "exec", "prompt"],
            returncode=0,
            stdout="  prose update\n",
            stderr="",
        ),
    ) as run:
        output = generate_prose("prompt")

    assert output == "prose update"
    run.assert_called_once_with(
        ["codex", "exec", "-"],
        input="prompt",
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_generate_prose_raises_when_codex_missing():
    with patch("surfwa.render.prose.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(CodexUnavailable):
            generate_prose("prompt")


def test_generate_prose_raises_on_timeout():
    with patch(
        "surfwa.render.prose.subprocess.run",
        side_effect=TimeoutExpired(cmd=["codex", "exec", "prompt"], timeout=180),
    ):
        with pytest.raises(CodexUnavailable) as excinfo:
            generate_prose("prompt")
    assert "prompt" not in str(excinfo.value)


def test_generate_prose_raises_on_launch_oserror_without_prompt_leak():
    with patch("surfwa.render.prose.subprocess.run", side_effect=OSError("boom prompt")):
        with pytest.raises(CodexUnavailable) as excinfo:
            generate_prose("SECRET PROMPT")
    assert "SECRET PROMPT" not in str(excinfo.value)


def test_generate_prose_raises_on_nonzero_return_code():
    with patch(
        "surfwa.render.prose.subprocess.run",
        return_value=CompletedProcess(
            args=["codex", "exec", "prompt"],
            returncode=1,
            stdout="",
            stderr="codex failed",
        ),
    ):
        with pytest.raises(CodexUnavailable, match="codex failed"):
            generate_prose("prompt")


def test_validate_prose_flags_invented_times():
    ok = validate_prose("Schev leuk 15-18u met fish.", [W])
    assert ok == []

    bad = validate_prose("Schev top 6-9u vroeg eruit!", [W])
    assert len(bad) == 1
    assert "6-9u" in bad[0]


def test_validate_prose_accepts_compact_nearby_time_ranges():
    assert validate_prose("Wijk 730-10u met fish.", [MORNING_WINDOW]) == []


def test_validate_prose_accepts_cross_midnight_time_ranges():
    assert validate_prose("IJmuiden 23-01u met fish.", [IJMUIDEN_LATE_WINDOW]) == []


def test_validate_prose_flags_time_ranges_for_wrong_spot():
    bad = validate_prose("Schev 730-10u met fish.", [W, MORNING_WINDOW])

    assert len(bad) == 1
    assert "730-10u" in bad[0]


def test_validate_prose_does_not_match_wijk_inside_nwijk():
    bad = validate_prose(
        "Nwijk 15-18u met fish.", [NOORDWIJK_WINDOW, WIJK_AFTERNOON_WINDOW]
    )

    assert len(bad) == 1
    assert "15-18u" in bad[0]


def test_validate_prose_recognizes_castricum_spot_context():
    bad = validate_prose(
        "Castricum 730-10u met fish.",
        [CASTRICUM_AFTERNOON_WINDOW, MORNING_WINDOW],
    )

    assert len(bad) == 1
    assert "730-10u" in bad[0]


def test_validate_prose_flags_grouped_spot_time_if_not_valid_for_all_spots():
    bad = validate_prose("Schev/Wijk 730-10u met fish.", [W, MORNING_WINDOW])

    assert len(bad) == 1
    assert "730-10u" in bad[0]


def test_validate_prose_flags_comma_grouped_spot_time_if_not_valid_for_all_spots():
    bad = validate_prose("Schev, Wijk 730-10u met fish.", [W, MORNING_WINDOW])

    assert len(bad) == 1
    assert "730-10u" in bad[0]


def test_validate_prose_recognizes_compact_wijkdorp_alias():
    bad = validate_prose(
        "WijkDorp 730-10u met fish.",
        [CASTRICUM_AFTERNOON_WINDOW, MORNING_WINDOW],
    )

    assert len(bad) == 1
    assert "730-10u" in bad[0]


def test_validate_prose_accepts_valid_adjacent_spot_sentences():
    assert (
        validate_prose("Schev 15-18u. Wijk 730-10u.", [W, MORNING_WINDOW])
        == []
    )


def test_validate_prose_accepts_valid_same_sentence_spot_clauses():
    assert (
        validate_prose("Schev 15-18u, Wijk 730-10u.", [W, MORNING_WINDOW])
        == []
    )


def test_validate_prose_keeps_spot_context_after_decimal_or_abbreviation():
    bad = validate_prose("Schev 0.9m v.a. 730-10u.", [W, MORNING_WINDOW])

    assert len(bad) == 1
    assert "730-10u" in bad[0]


def test_generate_update_falls_back_when_codex_unavailable():
    with patch(
        "surfwa.render.prose.generate_prose",
        side_effect=CodexUnavailable("no codex"),
    ):
        output = generate_update([W], "STRUCTURED TABLE")

    assert "STRUCTURED TABLE" in output
    assert "codex" in output.lower()
