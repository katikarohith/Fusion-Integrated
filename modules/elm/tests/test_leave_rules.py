from datetime import date
from decimal import Decimal

import pytest

from modules.elm.domain.leave_rules import (
    CalendarFacts,
    RuleViolation,
    count_and_split,
    has_overlap,
    in_vacation_period,
    year_end_outcome,
)


def test_working_day_categories_use_calendar_and_skip_closed_days():
    facts = CalendarFacts(
        closed_dates=frozenset({date(2026, 1, 2)}),
        closed_weekdays=frozenset({5, 6}),
    )
    total, years = count_and_split(
        "CL",
        date(2026, 1, 1),
        date(2026, 1, 4),
        "full",
        "working",
        {2026: facts},
    )
    assert total == Decimal("1.00")
    assert years == {2026: Decimal("1.00")}


def test_continuous_leave_counts_weekends_and_closed_dates():
    facts = CalendarFacts(
        closed_dates=frozenset({date(2026, 1, 2)}),
        closed_weekdays=frozenset({5, 6}),
    )
    total, _ = count_and_split(
        "EL",
        date(2026, 1, 1),
        date(2026, 1, 4),
        "full",
        "continuous",
        {2026: facts},
    )
    assert total == Decimal("4.00")


def test_half_day_cl_consumes_half_a_day():
    total, by_year = count_and_split(
        "CL",
        date(2026, 2, 2),
        date(2026, 2, 2),
        "first_half",
        "working",
        {2026: CalendarFacts()},
    )
    assert total == Decimal("0.50")
    assert by_year == {2026: Decimal("0.50")}


def test_half_day_is_not_supported_for_other_categories_or_multi_day_periods():
    with pytest.raises(RuleViolation, match="Half-day"):
        count_and_split(
            "SCL",
            date(2026, 2, 2),
            date(2026, 2, 2),
            "first_half",
            "working",
            {2026: CalendarFacts()},
        )
    with pytest.raises(RuleViolation, match="Half-day"):
        count_and_split(
            "CL",
            date(2026, 2, 2),
            date(2026, 2, 3),
            "first_half",
            "working",
            {2026: CalendarFacts()},
        )


def test_restricted_holiday_requires_a_published_calendar_date():
    with pytest.raises(RuleViolation, match="restricted-holiday"):
        count_and_split(
            "RH",
            date(2026, 2, 2),
            date(2026, 2, 2),
            "full",
            "restricted_holiday",
            {2026: CalendarFacts()},
        )


def test_only_opposite_cl_halves_on_the_same_day_do_not_overlap():
    existing = [("CL", date(2026, 2, 2), date(2026, 2, 2), "first_half")]
    assert not has_overlap(date(2026, 2, 2), date(2026, 2, 2), "second_half", existing)
    assert has_overlap(date(2026, 2, 2), date(2026, 2, 2), "first_half", existing)
    assert has_overlap(date(2026, 2, 2), date(2026, 2, 2), "full", existing)


def test_vacation_coverage_can_span_adjacent_calendar_snapshots():
    periods = (
        (date(2026, 12, 20), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 10)),
    )
    assert in_vacation_period(date(2026, 12, 24), date(2027, 1, 8), periods)
    assert not in_vacation_period(date(2026, 12, 19), date(2027, 1, 8), periods)


def test_year_end_lapses_cl_and_converts_vl_at_two_to_one_including_fraction():
    cl = year_end_outcome("CL", Decimal("8"), False)
    assert cl.carry_forward == Decimal("0.00")
    assert cl.lapse == Decimal("8")
    vl = year_end_outcome("VL", Decimal("5.50"), False)
    assert vl.lapse == Decimal("5.50")
    assert vl.vacation_to_earned == Decimal("2.75")


def test_year_end_carries_only_the_configured_earned_balance_amount():
    outcome = year_end_outcome("EL", Decimal("31"), True, Decimal("25"))
    assert outcome.carry_forward == Decimal("25")
    assert outcome.lapse == Decimal("6")
