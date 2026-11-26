"""The pure calculation of averages (`grades/averages.py`) against the plan's fixture table
(docs/slices/1b-slice-1.md § Fixture, in `fixtures/averages_cases.json`), with no database."""

import copy
import importlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from grades import average_data, averages

CASES = json.loads((Path(__file__).parent / "fixtures" / "averages_cases.json").read_text())[
    "cases"
]


@pytest.fixture(autouse=True)
def _as_app_role():
    """Overrides the gradebook conftest's: these tests need no database."""


def circular_rules():
    """The Circular 22/2021 rules as the migrations seed them (schools 0004, then 0007)."""
    seed = importlib.import_module("schools.migrations.0004_seed_secondary_assessment_profile")
    start = importlib.import_module("schools.migrations.0007_secondary_profile_from_2024")
    return {**copy.deepcopy(seed.RULES), **start.ADDED}


def key(name):
    kind, index = name.split()
    return kind, int(index)


def cells(given):
    return {
        key(name): (raw if raw in ("pass", "fail") else Decimal(raw)) for name, raw in given.items()
    }


def columns(book):
    """The book's columns as opening a gradebook creates them (regular, mid-term, end-term),
    through `average_data.required`."""
    made = [("regular", i) for i in range(1, book["regular"] + 1)]
    made += [("mid_term", 1), ("end_term", 1)]
    return average_data.required([SimpleNamespace(kind=kind, index=index) for kind, index in made])


def semester(rules, book):
    return averages.semester(
        rules,
        book["assessment"],
        columns(book),
        cells(book["local"]),
        cells(book["carried"]),
        book["status"],
        left=book.get("left", False),
        split=book.get("split", False),
    )


def compute(case, rules=None):
    rules = rules or circular_rules()
    book = semester(rules, case["book"])
    first = semester(rules, case["first"]) if "first" in case else None
    previous = Decimal(case["previous"]) if case.get("previous") else None
    terms, earlier = case["terms"]
    year = averages.year(rules, case["book"]["assessment"], terms, earlier, first, previous, book)
    return {"semester": book, "first": first, "year": year}


def as_expected(average, expected):
    """The fields of `average` the case states, in the fixture's form."""
    if average is None or expected is None:
        return average if expected is None else None
    shown = {
        "value": None if average.value is None else str(average.value),
        "result": average.result,
        "state": average.state,
        "missing": [f"{kind} {index}" for kind, index in average.missing],
        "carried": average.carried,
        "reason": average.reason,
    }
    return {name: shown[name] for name in expected}


@pytest.mark.parametrize("case", CASES, ids=[f"case_{c['id']}" for c in CASES])
def test_the_fixture_case_matches(case):
    got = compute(case)
    for part, expected in case["expected"].items():
        assert as_expected(got[part], expected) == expected, part


def test_a_semester_average_is_rounded_to_the_profiles_decimals_never_the_context_default():
    got = compute(next(c for c in CASES if c["id"] == "B"))["semester"]
    assert got.value == Decimal("7.3") and got.value.as_tuple().exponent == -1


def test_a_carried_cell_used_in_a_semester_is_flagged():
    case = next(c for c in CASES if c["id"] == "E")
    assert compute(case)["semester"].carried is True
    plain = next(c for c in CASES if c["id"] == "A")
    assert compute(plain)["semester"].carried is False
    over = next(c for c in CASES if c["id"] == "M")  # the local score won: nothing carried used
    assert compute(over)["semester"].carried is False


@pytest.mark.parametrize(
    "drop",
    [("weights",), ("rounding",), ("scale",), ("year_average",)],
    ids=lambda d: "/".join(d),
)
def test_a_profile_version_lacking_a_key_gives_unavailable_never_a_guess(drop):
    rules = circular_rules()
    del rules[drop[0]]
    case = next(c for c in CASES if c["id"] == "C")
    got = compute(case, rules)
    states = {name: got[name].state for name in ("semester", "first", "year")}
    if drop[0] == "year_average":
        assert states == {"semester": "final", "first": "final", "year": "unavailable"}
    else:
        assert set(states.values()) == {"unavailable"}
    assert got["year"].reason == "rules" and got["year"].value is None


def test_an_unknown_rounding_mode_or_year_without_rounded_semesters_is_unavailable():
    case = next(c for c in CASES if c["id"] == "C")
    for change in ({"rounding": "ROUND_SOMEHOW"}, {"rounding": "__name__"}):
        assert compute(case, {**circular_rules(), **change})["semester"].reason == "rules"
    unrounded = {**circular_rules(), "year_average_uses_rounded_semester_averages": False}
    assert compute(case, unrounded)["year"].state == "unavailable"


def test_the_states_follow_their_precedence():
    case = next(c for c in CASES if c["id"] == "F")  # missing, and also left
    left = copy.deepcopy(case)
    left["book"]["left"] = True
    assert compute(left)["semester"].state == "left"
    # The year takes the worse of the two semesters: a missing S2 beats a final S1.
    year_case = copy.deepcopy(next(c for c in CASES if c["id"] == "C"))
    year_case["book"]["local"].pop("end_term 1")
    year = compute(year_case)["year"]
    assert (year.state, year.value) == ("missing", None)


def test_the_year_lists_no_missing_column_of_the_other_semesters_book():
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "C"))
    case["first"]["status"] = "draft"
    case["first"]["local"].pop("end_term 1")
    got = compute(case)
    assert got["first"].missing == (("end_term", 1),)
    assert (got["year"].state, got["year"].missing) == ("missing", ())


def test_the_required_columns_follow_the_column_order_whatever_order_they_are_read_in():
    read = [("end_term", 1), ("regular", 2), ("mid_term", 1), ("regular", 1)]
    got = average_data.required([SimpleNamespace(kind=kind, index=index) for kind, index in read])
    assert got == [("regular", 1), ("regular", 2), ("mid_term", 1), ("end_term", 1)]
