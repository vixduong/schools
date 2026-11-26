"""Semester and year averages of one student in one subject (Circular 22/2021 Art. 9.1,
docs/slices/1b-slice-1.md), pure: no ORM and no clock. Weights and rounding come from the profile
version's `rules` (ADR 0006); a version lacking a key the calculation needs gives `unavailable`
(reason `rules`), never a guess. `average_data.py` gathers the inputs."""

import decimal
from dataclasses import dataclass
from decimal import Decimal

# Worst first: a student's state is the first of these that applies.
STATES = ("unavailable", "split", "left", "missing", "provisional", "final")
ROUNDINGS = {
    name
    for name in dir(decimal)
    if name.startswith("ROUND_") and isinstance(getattr(decimal, name), str)
}


@dataclass(frozen=True)
class Average:
    """`value` for a scored subject, `result` (`pass`/`fail`) for a comment-only one, either
    only when `state` is `final` or `provisional`. `missing`: the empty required columns, as
    (kind, index). `carried`: a carried result was used. `reason`: why `unavailable` (`rules`,
    `terms`) or a year is `missing` (`no_previous_average`)."""

    value: Decimal | None
    result: str | None
    state: str
    missing: tuple = ()
    carried: bool = False
    reason: str | None = None


UNAVAILABLE_RULES = Average(None, None, "unavailable", reason="rules")


def rounded(rules, number):
    """`number` to the scale's decimals with the profile's rounding mode, passed explicitly: the
    context default is half-even."""
    if rules["rounding"] not in ROUNDINGS:
        raise KeyError("rounding")
    step = Decimal(1).scaleb(-rules["scale"]["decimals"])
    return number.quantize(step, rounding=getattr(decimal, rules["rounding"]))


def semester(rules, assessment, columns, local, carried, status, left=False, split=False):
    """One gradebook's average for one student. `columns`: the required (kind, index) cells;
    `local` and `carried`: {(kind, index): Decimal or "pass"/"fail"} of the current, not cleared,
    entries and carried results. A local score wins over a carried one. `status` is the
    gradebook's; `left` and `split` as in the plan's states."""
    try:
        if assessment == "scored":
            required = [rules["weights"][kind] for kind, _ in columns]
            rounded(rules, Decimal(0))
    except (KeyError, TypeError):
        return UNAVAILABLE_RULES
    if split:
        return Average(None, None, "split")
    if left:
        return Average(None, None, "left")
    values, used_carried, missing = [], False, []
    for column in columns:
        value = local.get(column)
        if value is None:
            value = carried.get(column)
            used_carried |= value is not None
        if value is None:
            missing.append(column)
        values.append(value)
    if missing:
        return Average(None, None, "missing", tuple(missing), used_carried)
    state = "final" if status == "approved" else "provisional"
    if assessment == "scored":
        total = sum(Decimal(w) * v for w, v in zip(required, values, strict=True))
        value = rounded(rules, total / sum(required))
        return Average(value, None, state, carried=used_carried)
    result = "pass" if all(v == "pass" for v in values) else "fail"
    return Average(None, result, state, carried=used_carried)


def year(rules, assessment, terms_in_year, earlier_terms, first, previous, second):
    """The year average, or None for a book that is not the second semester's. `terms_in_year`:
    the terms of the school year; `earlier_terms`: those ending before the book's term starts.
    `second`: this book's semester average; `first`: the student's own semester 1 average (None
    without a semester 1 gradebook); `previous`: their carried previous semester average, used
    only without `first`."""
    if terms_in_year != 2:
        return Average(None, None, "unavailable", reason="terms")
    if earlier_terms == 0:
        return None
    if assessment != "scored":  # the year result is semester 2's
        return second
    try:
        weights = rules["year_average"]["weights"]
        w1, w2 = Decimal(weights["semester_1"]), Decimal(weights["semester_2"])
        rounded(rules, Decimal(0))
        # schema 1 only states the rounded form; an unrounded rule would need its own inputs
        if rules["year_average_uses_rounded_semester_averages"] is not True:
            raise KeyError("year_average_uses_rounded_semester_averages")
    except (KeyError, TypeError):
        return UNAVAILABLE_RULES
    if first is None:
        first = (
            Average(previous, None, "final", carried=True)
            if previous is not None
            else Average(None, None, "missing", reason="no_previous_average")
        )
    worse = min((first, second), key=lambda a: STATES.index(a.state))
    if worse.state not in ("final", "provisional"):
        return Average(None, None, worse.state, worse.missing, first.carried, worse.reason)
    value = rounded(rules, (w1 * first.value + w2 * second.value) / (w1 + w2))
    return Average(value, None, worse.state, carried=first.carried)
