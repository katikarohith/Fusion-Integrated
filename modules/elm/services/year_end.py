"""Idempotent annual entitlement, lapse, carry-forward, and VL conversion."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.api.exceptions import ConflictError
from modules.directory import contracts as directory
from modules.elm.domain.leave_rules import year_end_outcome
from modules.elm.models import (
    LeaveLedgerEntry,
    LeavePolicy,
    YearEndItem,
    YearEndRun,
)
from modules.elm.services.accounts import account_for
from modules.elm.services.workflow import require

ZERO = Decimal("0.00")


@transaction.atomic
def process_year_end(*, year: int, actor_user_id: int | None = None):
    year = int(year)
    if year >= timezone.localdate().year:
        raise ConflictError(
            "Year-end processing is available only after that year ends.", code="year_not_closed"
        )
    run, _ = YearEndRun.objects.get_or_create(
        year=year, defaults={"processed_by_user_id": actor_user_id, "status": "running"}
    )
    run = YearEndRun.objects.select_for_update().get(pk=run.pk)
    if run.status == "completed":
        return run
    run.status = "running"
    run.processed_by_user_id = actor_user_id
    run.completed_at = None
    run.save(update_fields=["status", "processed_by_user_id", "completed_at", "updated_at"])

    employees = directory.get_employees()
    policies = list(LeavePolicy.objects.filter(is_active=True).select_related("leave_type"))
    totals = {
        "accounts_processed": 0,
        "lapsed_days": ZERO,
        "carried_forward_days": ZERO,
        "vl_converted_to_el": ZERO,
        "exceptions": [],
    }
    for employee in employees:
        applicable = [p for p in policies if p.employee_kind == employee.kind]
        for policy in applicable:
            old, _ = account_for(
                employee_user_id=employee.user_id,
                leave_type=policy.leave_type,
                employee_kind=employee.kind,
                year=year,
                for_update=True,
            )
            item, _ = YearEndItem.objects.get_or_create(
                run=run,
                balance=old,
                defaults={"status": "failed", "details": {}},
            )
            if item.status == "completed":
                totals["accounts_processed"] += 1
                totals["lapsed_days"] += Decimal(item.details.get("lapse", "0"))
                totals["carried_forward_days"] += Decimal(item.details.get("carry_forward", "0"))
                totals["vl_converted_to_el"] += Decimal(item.details.get("vl_to_el", "0"))
                continue
            if old.reserved > ZERO:
                item.status = "failed"
                item.details = {"reason": "pending_reservations", "reserved": str(old.reserved)}
                item.save(update_fields=["status", "details", "updated_at"])
                totals["exceptions"].append(
                    {
                        "employee_user_id": employee.user_id,
                        "leave_type": policy.leave_type.code,
                        "reason": "pending_reservations",
                    }
                )
                continue

            unused = max(old.available, ZERO)
            outcome = year_end_outcome(
                policy.leave_type.code,
                unused,
                policy.carry_forward,
                policy.carry_forward_limit,
            )
            earned_leave_type = None
            if outcome.vacation_to_earned > ZERO:
                earned_leave_type = next(
                    (
                        p.leave_type
                        for p in policies
                        if p.employee_kind == employee.kind and p.leave_type.code == "EL"
                    ),
                    None,
                )
                if earned_leave_type is None:
                    item.status = "failed"
                    item.details = {"reason": "faculty_earned_leave_policy_missing"}
                    item.save(update_fields=["status", "details", "updated_at"])
                    totals["exceptions"].append(
                        {
                            "employee_user_id": employee.user_id,
                            "leave_type": "VL",
                            "reason": "faculty_earned_leave_policy_missing",
                        }
                    )
                    continue

            if outcome.lapse > ZERO:
                _entry, created = LeaveLedgerEntry.objects.get_or_create(
                    idempotency_key=f"yearend-lapse:{year}:{old.pk}",
                    defaults={
                        "balance": old,
                        "amount": -outcome.lapse,
                        "kind": "lapse",
                        "source_kind": "year_end",
                        "source_id": year,
                        "actor_user_id": actor_user_id,
                        "reason": f"Unused {policy.leave_type.code} lapsed at year end",
                    },
                )
                if created:
                    old.expired += outcome.lapse
                    old.save(update_fields=["expired", "updated_at"])
                    totals["lapsed_days"] += outcome.lapse

            if outcome.carry_forward > ZERO:
                next_balance, _ = account_for(
                    employee_user_id=employee.user_id,
                    leave_type=policy.leave_type,
                    employee_kind=employee.kind,
                    year=year + 1,
                    for_update=True,
                )
                _, created = LeaveLedgerEntry.objects.get_or_create(
                    idempotency_key=f"yearend-carry:{year}:{old.pk}",
                    defaults={
                        "balance": next_balance,
                        "amount": outcome.carry_forward,
                        "kind": "carry",
                        "source_kind": "year_end",
                        "source_id": year,
                        "actor_user_id": actor_user_id,
                        "reason": f"Carry-forward from {year}",
                    },
                )
                if created:
                    next_balance.carried_forward += outcome.carry_forward
                    next_balance.save(update_fields=["carried_forward", "updated_at"])
                    totals["carried_forward_days"] += outcome.carry_forward

            if outcome.vacation_to_earned > ZERO:
                earned_balance, _ = account_for(
                    employee_user_id=employee.user_id,
                    leave_type=earned_leave_type,
                    employee_kind=employee.kind,
                    year=year + 1,
                    for_update=True,
                )
                _, created = LeaveLedgerEntry.objects.get_or_create(
                    idempotency_key=f"yearend-vl-conversion:{year}:{old.pk}",
                    defaults={
                        "balance": earned_balance,
                        "amount": outcome.vacation_to_earned,
                        "kind": "conversion",
                        "source_kind": "year_end",
                        "source_id": year,
                        "actor_user_id": actor_user_id,
                        "reason": "Unused faculty VL converted to EL at 2:1",
                    },
                )
                if created:
                    earned_balance.adjustments += outcome.vacation_to_earned
                    earned_balance.save(update_fields=["adjustments", "updated_at"])
                    totals["vl_converted_to_el"] += outcome.vacation_to_earned

            item.status = "completed"
            item.details = {
                "unused": str(unused),
                "carry_forward": str(outcome.carry_forward),
                "lapse": str(outcome.lapse),
                "vl_to_el": str(outcome.vacation_to_earned),
            }
            item.save(update_fields=["status", "details", "updated_at"])
            totals["accounts_processed"] += 1

    totals["lapsed_days"] = str(totals["lapsed_days"])
    totals["carried_forward_days"] = str(totals["carried_forward_days"])
    totals["vl_converted_to_el"] = str(totals["vl_converted_to_el"])
    run.summary = totals
    run.status = "failed" if totals["exceptions"] else "completed"
    run.completed_at = timezone.now() if run.status == "completed" else None
    run.save(update_fields=["summary", "status", "completed_at", "updated_at"])
    return run


def run_year_end(actor, *, year: int):
    require(actor, "leave_elm.year_end.process")
    return process_year_end(year=year, actor_user_id=actor.user_id)
