"""Pure ELM policy arithmetic; no Django or HTTP dependencies."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

HALF = Decimal("0.50")
ZERO = Decimal("0.00")
CONTINUOUS_TYPES = frozenset({"EL", "COL", "VL"})
SUPPORTED_TYPES = frozenset({"CL", "RH", "SCL", "EL", "COL", "VL"})


class RuleViolation(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CalendarFacts:
    closed_dates: frozenset[date] = frozenset()
    restricted_holidays: frozenset[date] = frozenset()
    closed_weekdays: frozenset[int] = frozenset()
    vacation_periods: tuple[tuple[date, date], ...] = ()


def dates_inclusive(start: date, end: date):
    if end < start:
        raise RuleViolation("invalid_dates", "End date must be on or after start date.")
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def count_and_split(
    category: str,
    start: date,
    end: date,
    day_part: str,
    counting_mode: str,
    calendars: dict[int, CalendarFacts],
) -> tuple[Decimal, dict[int, Decimal]]:
    """Count a request, preserving annual account allocation.

    EL/COL/VL use continuous inclusive counting. Other categories use the
    configured working-day or restricted-holiday calendar rules. Half-day CL
    consumes exactly 0.5 day and can only cover one date.
    """
    if category not in SUPPORTED_TYPES:
        raise RuleViolation("unsupported_leave_type", "This leave category is not supported.")
    if end < start:
        raise RuleViolation("invalid_dates", "End date must be on or after start date.")
    if day_part not in {"full", "first_half", "second_half"}:
        raise RuleViolation("invalid_day_part", "Choose a supported day part.")
    if day_part != "full" and (category != "CL" or start != end):
        raise RuleViolation(
            "invalid_half_day", "Half-day requests are available for one-day CL only."
        )
    if category in CONTINUOUS_TYPES and counting_mode != "continuous":
        raise RuleViolation("invalid_policy", "EL, COL, and VL must use continuous-day counting.")
    if category == "RH" and counting_mode != "restricted_holiday":
        raise RuleViolation(
            "invalid_policy", "RH requests must use the restricted-holiday calendar."
        )

    pieces: dict[int, Decimal] = defaultdict(lambda: ZERO)
    if counting_mode == "restricted_holiday":
        facts = calendars.get(start.year)
        if start != end or facts is None or start not in facts.restricted_holidays:
            raise RuleViolation(
                "not_restricted_holiday",
                "Select a date in the current published restricted-holiday calendar.",
            )
        pieces[start.year] = Decimal("1.00")
    else:
        for day in dates_inclusive(start, end):
            facts = calendars.get(day.year)
            if facts is None:
                raise RuleViolation(
                    "calendar_unavailable",
                    f"No published leave calendar is available for {day.year}.",
                )
            if counting_mode == "continuous":
                included = True
            elif counting_mode == "working":
                included = (
                    day not in facts.closed_dates and day.weekday() not in facts.closed_weekdays
                )
            else:
                raise RuleViolation(
                    "invalid_policy", "The configured leave counting mode is invalid."
                )
            if included:
                pieces[day.year] += Decimal("1.00")

    if not pieces or sum(pieces.values(), ZERO) == ZERO:
        raise RuleViolation(
            "no_countable_days", "The requested period contains no countable leave days."
        )
    if day_part != "full":
        pieces[start.year] = HALF
    return sum(pieces.values(), ZERO), dict(pieces)


def has_overlap(
    start: date,
    end: date,
    day_part: str,
    existing: list[tuple[str, date, date, str]],
) -> bool:
    """Return whether a pending/approved interval overlaps the candidate.

    The sole overlap exception is first-half and second-half CL on the same date.
    """
    for category, other_start, other_end, other_part in existing:
        if start > other_end or end < other_start:
            continue
        if (
            category == "CL"
            and start == end == other_start == other_end
            and {day_part, other_part} == {"first_half", "second_half"}
        ):
            continue
        return True
    return False


def in_vacation_period(start: date, end: date, periods: tuple[tuple[date, date], ...]) -> bool:
    if end < start:
        return False
    ordered = sorted(periods)
    covered_until = None
    for period_start, period_end in ordered:
        if period_end < start or period_start > end:
            continue
        if covered_until is None:
            if period_start > start:
                return False
            covered_until = period_end
        elif period_start <= covered_until + timedelta(days=1):
            covered_until = max(covered_until, period_end)
        elif covered_until < end:
            return False
        if covered_until >= end:
            return True
    return False


@dataclass(frozen=True)
class YearEndOutcome:
    carry_forward: Decimal
    lapse: Decimal
    vacation_to_earned: Decimal


def year_end_outcome(
    category: str,
    unused: Decimal,
    carry_forward_enabled: bool,
    carry_forward_limit: Decimal | None = None,
) -> YearEndOutcome:
    """Apply the synchronized baseline's lapse, carry, and 2:1 VL conversion."""
    unused = max(Decimal("0.00"), Decimal(unused))
    if category == "VL":
        converted = (unused / Decimal("2")).quantize(Decimal("0.01"))
        return YearEndOutcome(ZERO, unused, converted)
    if category in {"EL", "COL"} and carry_forward_enabled:
        carried = min(unused, carry_forward_limit) if carry_forward_limit is not None else unused
        return YearEndOutcome(carried, unused - carried, ZERO)
    return YearEndOutcome(ZERO, unused, ZERO)


ACTIVE_APPLICATION_STATES = frozenset(
    {
        "awaiting_substitute",
        "applicant_action_required",
        "pending_approval",
        "approved",
        "cancellation_pending",
    }
)
TERMINAL_APPLICATION_STATES = frozenset({"rejected", "withdrawn", "cancelled"})


def may_withdraw(status: str) -> bool:
    return status in {"awaiting_substitute", "applicant_action_required", "pending_approval"}


def may_cancel_approved(status: str, start: date, today: date) -> bool:
    return status == "approved" and today < start


def may_extend(category: str, status: str, start: date, end: date, today: date) -> bool:
    return category in CONTINUOUS_TYPES and status == "approved" and start <= today <= end


def may_resume(category: str, status: str) -> bool:
    return category in CONTINUOUS_TYPES and status == "approved"
