"""Balance locking, reservation and append-only ledger operations."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from core.api.exceptions import ConflictError, NotFoundError
from modules.elm.models import (
    LeaveBalance,
    LeaveLedgerEntry,
    LeavePolicy,
    LeaveReservation,
)

ZERO = Decimal("0.00")


def ledger(
    *, balance, amount, kind, actor_user_id=None, source_kind="", source_id=None, reason="", key
):
    entry, created = LeaveLedgerEntry.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "balance": balance,
            "amount": amount,
            "kind": kind,
            "actor_user_id": actor_user_id,
            "source_kind": source_kind,
            "source_id": source_id,
            "reason": reason[:500],
        },
    )
    if not created and (
        entry.balance_id != balance.id or entry.amount != amount or entry.kind != kind
    ):
        raise ConflictError(
            "The ledger idempotency key was reused for a different entry.",
            code="ledger_key_conflict",
        )
    return entry


def account_for(*, employee_user_id, leave_type, employee_kind, year, for_update=False):
    try:
        policy = LeavePolicy.objects.get(
            leave_type=leave_type, employee_kind=employee_kind, is_active=True
        )
    except LeavePolicy.DoesNotExist as exc:
        raise NotFoundError(
            "No active policy applies to this employee and leave category.",
            code="policy_not_configured",
        ) from exc

    balance, created = LeaveBalance.objects.get_or_create(
        employee_user_id=employee_user_id,
        leave_type=leave_type,
        year=year,
        defaults={"allotted": policy.annual_entitlement},
    )
    if for_update:
        balance = LeaveBalance.objects.select_for_update().get(pk=balance.pk)
    if created:
        ledger(
            balance=balance,
            amount=policy.annual_entitlement,
            kind="credit",
            source_kind="annual",
            source_id=year,
            reason=f"Annual {year} entitlement",
            key=f"annual:{employee_user_id}:{leave_type.pk}:{year}",
        )
    return balance, policy


@transaction.atomic
def reserve(
    *, subject, subject_field, employee_user_id, employee_kind, leave_type, by_year, actor_user_id
):
    if subject_field not in {"application", "action_request"}:
        raise ValueError("subject_field must be application or action_request")
    reservations = []
    for year, amount in sorted(by_year.items()):
        amount = Decimal(amount)
        if amount <= ZERO:
            continue
        balance, _ = account_for(
            employee_user_id=employee_user_id,
            leave_type=leave_type,
            employee_kind=employee_kind,
            year=year,
            for_update=True,
        )
        if balance.available < amount:
            raise ConflictError(
                f"Insufficient {leave_type.code} balance for {year}.",
                code="insufficient_balance",
                details=[
                    {"year": year, "available": str(balance.available), "requested": str(amount)}
                ],
            )
        balance.reserved += amount
        balance.save(update_fields=["reserved", "updated_at"])
        reservation = LeaveReservation.objects.create(
            **{subject_field: subject}, balance=balance, days=amount
        )
        ledger(
            balance=balance,
            amount=-amount,
            kind="reserve",
            actor_user_id=actor_user_id,
            source_kind=subject_field,
            source_id=subject.pk,
            reason="Leave days reserved pending sanction",
            key=f"reserve:{subject_field}:{subject.pk}:{year}",
        )
        reservations.append(reservation)
    return reservations


@transaction.atomic
def release_reservations(*, subject, subject_field, actor_user_id, reason):
    qs = (
        LeaveReservation.objects.select_for_update()
        .filter(**{subject_field: subject}, status="reserved")
        .select_related("balance")
    )
    for reservation in qs:
        balance = LeaveBalance.objects.select_for_update().get(pk=reservation.balance_id)
        balance.reserved -= reservation.days
        if balance.reserved < ZERO:
            raise ConflictError(
                "Leave reservation accounting is inconsistent.", code="balance_invariant"
            )
        balance.save(update_fields=["reserved", "updated_at"])
        reservation.status = "released"
        reservation.save(update_fields=["status", "updated_at"])
        ledger(
            balance=balance,
            amount=reservation.days,
            kind="release",
            actor_user_id=actor_user_id,
            source_kind=subject_field,
            source_id=subject.pk,
            reason=reason,
            key=f"release:{subject_field}:{subject.pk}:{balance.year}",
        )


@transaction.atomic
def post_reservations(*, subject, subject_field, actor_user_id):
    qs = (
        LeaveReservation.objects.select_for_update()
        .filter(**{subject_field: subject}, status="reserved")
        .select_related("balance")
    )
    for reservation in qs:
        balance = LeaveBalance.objects.select_for_update().get(pk=reservation.balance_id)
        balance.reserved -= reservation.days
        balance.used += reservation.days
        if balance.reserved < ZERO:
            raise ConflictError(
                "Leave reservation accounting is inconsistent.", code="balance_invariant"
            )
        balance.save(update_fields=["reserved", "used", "updated_at"])
        reservation.status = "posted"
        reservation.save(update_fields=["status", "updated_at"])
        ledger(
            balance=balance,
            amount=-reservation.days,
            kind="use",
            actor_user_id=actor_user_id,
            source_kind=subject_field,
            source_id=subject.pk,
            reason="Sanctioned leave",
            key=f"use:{subject_field}:{subject.pk}:{balance.year}",
        )


@transaction.atomic
def reverse_application_usage(*, application, actor_user_id, reason):
    qs = (
        LeaveReservation.objects.select_for_update()
        .filter(application=application, status="posted")
        .select_related("balance")
    )
    for reservation in qs:
        balance = LeaveBalance.objects.select_for_update().get(pk=reservation.balance_id)
        balance.used -= reservation.days
        if balance.used < ZERO:
            raise ConflictError(
                "The leave account cannot reverse more usage than it contains.",
                code="balance_invariant",
            )
        balance.save(update_fields=["used", "updated_at"])
        reservation.status = "released"
        reservation.save(update_fields=["status", "updated_at"])
        ledger(
            balance=balance,
            amount=reservation.days,
            kind="cancellation",
            actor_user_id=actor_user_id,
            source_kind="application",
            source_id=application.pk,
            reason=reason,
            key=f"cancel:{application.pk}:{balance.year}",
        )


@transaction.atomic
def adjust_used(
    *,
    employee_user_id,
    leave_type,
    employee_kind,
    by_year,
    actor_user_id,
    source_kind,
    source_id,
    reason,
):
    for year, delta in sorted(by_year.items()):
        delta = Decimal(delta)
        if delta == ZERO:
            continue
        balance, _ = account_for(
            employee_user_id=employee_user_id,
            leave_type=leave_type,
            employee_kind=employee_kind,
            year=year,
            for_update=True,
        )
        new_used = balance.used + delta
        if new_used < ZERO:
            raise ConflictError(
                "The leave account cannot reverse more usage than it contains.",
                code="balance_invariant",
            )
        balance.used = new_used
        balance.save(update_fields=["used", "updated_at"])
        ledger(
            balance=balance,
            amount=-delta,
            kind="resumption",
            actor_user_id=actor_user_id,
            source_kind=source_kind,
            source_id=source_id,
            reason=reason,
            key=f"usage-adjust:{source_kind}:{source_id}:{year}",
        )
