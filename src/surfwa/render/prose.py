from __future__ import annotations

from datetime import timedelta
import re
import subprocess

from surfwa.render.structured import windows_to_json
from surfwa.score import Window


class CodexUnavailable(Exception):
    pass


_INSTRUCTIONS = """Je schrijft een Nederlandse surf-update in compacte telegramstijl.

Regels:
- Gebruik UITSLUITEND de spots, tijden, hoogtes en periodes uit de JSON. Verzin geen extra spots, tijden of metingen.
- Gebruik spot-afkortingen waar natuurlijk: Schev, Mvlakte, HvH, Nwijk, Zvoort, Wijk, IJmuiden.
- Schrijf tijden compact als '15-18u' of '2030-22u'.
- Noem per dag de beste opties eerst, per spot het tijdvenster en het board.
- Neem waarschuwingen zoals stroming letterlijk mee.
- Houd het droog en praktisch, met hooguit een klein beetje droge humor.
- Maximaal 180 woorden. Geen aanhef, geen afsluiting, alleen de update.

DATA (JSON):
{data}
"""

_TIME_RANGE = re.compile(r"\b(\d{1,4})-(\d{1,4})u\b")
_SPOT_ALIASES = {
    "scheveningen": ("schev", "scheveningen"),
    "maasvlakte": ("mvlakte", "maasvlakte"),
    "hoek-van-holland": ("hvh", "hoek"),
    "noordwijk": ("nwijk", "noordwijk"),
    "zandvoort": ("zvoort", "zandvoort"),
    "wijk-aan-zee": ("wijk", "wijk aan zee"),
    "ijmuiden": ("ijmuiden",),
    "ter-heijde": ("terheijde", "ter heijde", "kijkduin", "monster"),
    "katwijk": ("katwijk",),
    "wassenaar": ("wssnaar", "wassenaar"),
    "egmond": ("egmond",),
    "bergen": ("bergen",),
    "camperduin": ("camperduin",),
    "castricum": ("castricum", "wijk dorp", "wijkdorp"),
    "petten": ("petten",),
}


def build_prompt(windows_json: str, style_examples: list[str]) -> str:
    return _INSTRUCTIONS.format(
        data=windows_json,
    )


def generate_prose(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["codex", "exec", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise CodexUnavailable("codex binary niet gevonden") from exc
    except subprocess.TimeoutExpired as exc:
        raise CodexUnavailable("codex exec timeout") from exc
    except OSError as exc:
        raise CodexUnavailable(f"codex exec kon niet starten ({type(exc).__name__})") from exc

    if result.returncode != 0:
        raise CodexUnavailable(result.stderr[:500])

    return result.stdout.strip()


def validate_prose(text: str, windows: list[Window]) -> list[str]:
    valid_hours_by_spot: dict[str, set[int]] = {}
    for window in windows:
        t = window.start - timedelta(hours=1)
        stop = window.end + timedelta(hours=1)
        while t <= stop:
            valid_hours_by_spot.setdefault(window.spot_slug, set()).add(t.hour)
            t += timedelta(hours=1)

    violations: list[str] = []
    for match in _TIME_RANGE.finditer(text):
        start_hour = _hour_from_token(match.group(1))
        end_hour = _hour_from_token(match.group(2))
        valid_hours = _valid_hours_for_match(text, match.start(), valid_hours_by_spot)
        if start_hour not in valid_hours or end_hour not in valid_hours:
            violations.append(f"tijd {match.group(0)} komt niet uit de data")

    return violations


def generate_update(windows: list[Window], fallback_structured: str) -> str:
    prompt = build_prompt(windows_to_json(windows), [])
    try:
        prose = generate_prose(prompt)
    except CodexUnavailable as exc:
        return (
            f"{fallback_structured}\n\n"
            f"[codex niet beschikbaar ({exc}); gestructureerde output getoond]"
        )

    violations = validate_prose(prose, windows)
    if violations:
        prose += "\n\n[validatie: " + "; ".join(violations) + "]"
    return prose


def _hour_from_token(token: str) -> int:
    if len(token) <= 2:
        return int(token)
    if len(token) == 3:
        return int(token[:1])
    return int(token[:2])


def _valid_hours_for_match(
    text: str,
    match_start: int,
    valid_hours_by_spot: dict[str, set[int]],
) -> set[int]:
    matched_sets: list[set[int]] = []
    for slug in _spot_slugs_for_match(text, match_start):
        matched_sets.append(set(valid_hours_by_spot.get(slug, set())))
    if matched_sets:
        valid = matched_sets[0]
        for hours in matched_sets[1:]:
            valid &= hours
        return valid
    all_hours: set[int] = set()
    for hours in valid_hours_by_spot.values():
        all_hours.update(hours)
    return all_hours


def _alias_in_context(alias: str, context: str) -> bool:
    escaped = re.escape(alias)
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", context) is not None


def _spot_slugs_for_match(text: str, match_start: int) -> list[str]:
    prefix = text[:match_start].lower()
    occurrences: list[tuple[int, int, str]] = []
    for slug, aliases in _SPOT_ALIASES.items():
        for alias in aliases:
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            for match in re.finditer(pattern, prefix):
                occurrences.append((match.start(), match.end(), slug))
    if not occurrences:
        return []

    occurrences.sort(key=lambda item: (item[0], item[1]))
    group = [max(occurrences, key=lambda item: (item[0], item[1]))]
    earliest_start = group[0][0]
    for start, end, slug in reversed(occurrences):
        if (start, end, slug) == group[0] or end > earliest_start:
            continue
        between = prefix[end:earliest_start]
        if not re.fullmatch(r"[\s,/&+]+", between):
            break
        group.append((start, end, slug))
        earliest_start = start

    slugs: list[str] = []
    for _, _, slug in sorted(group, key=lambda item: item[0]):
        if slug not in slugs:
            slugs.append(slug)
    return slugs
