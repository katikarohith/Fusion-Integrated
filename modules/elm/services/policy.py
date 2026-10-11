"""Administrative ELM configuration and record-maintenance services."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.api.exceptions import ConflictError, NotFoundError
from modules.directory import contracts as directory
from modules.elm.domain import leave_rules as rules
from modules.elm.models import (
    CalendarDate,
    EmployeeProfile,
    LeaveApplication,
    LeaveBalance,
    LeaveCalendar,
    LeaveConfigurationEvent,
    LeaveLedgerEntry,
    LeavePolicy,
    LeaveType,
    RouteRule,
    RouteStep,
    SlaPolicy,
    VacationPeriod,
    WorkflowTask,
)
from modules.elm.services import accounts
from modules.elm.services.workflow import (
    calendar_facts,
    record_event,
    require,
    validate_route,
)


def _configuration_event(actor, event, object_kind, object_id, details):
    return LeaveConfigurationEvent.objects.create(
        actor_user_id=actor.user_id,
        event=event,
        object_kind=object_kind,
        object_id=object_id,
        details=details,
    )


def update_policy(
    actor,
    *,
    leave_type_code,
    employee_kind,
    annual_entitlement,
    carry_forward,
    carry_forward_limit=None,
    counting_mode="working",
    requires_medical_evidence=False,
    requires_vacation_period=False,
):
    require(actor, "leave_elm.policy.manage")
    try:
        leave_type = LeaveType.objects.get(code=leave_type_code, is_active=True)
    except LeaveType.DoesNotExist as exc:
        raise NotFoundError("Leave category not found.", code="not_found") from exc
    amount = Decimal(annual_entitlement)
    limit = Decimal(carry_forward_limit) if carry_forward_limit is not None else None
    if amount < 0 or (limit is not None and limit < 0):
        raise ConflictError(
            "Entitlements and carry-forward limits cannot be negative.", code="invalid_policy"
        )
    if leave_type.code in rules.CONTINUOUS_TYPES and counting_mode != "continuous":
        raise ConflictError("EL, COL, and VL use continuous-day counting.", code="invalid_policy")
    if leave_type.code == "RH" and counting_mode != "restricted_holiday":
        raise ConflictError(
            "RH uses the published restricted-holiday calendar.", code="invalid_policy"
        )
    if leave_type.code not in {"EL", "COL"} and carry_forward:
        raise ConflictError(
            "Only EL and COL carry forward under the current specification.", code="invalid_policy"
        )
    if leave_type.code == "VL" and carry_forward:
        raise ConflictError(
            "VL converts to EL at year end; it does not carry forward.", code="invalid_policy"
        )
    policy, _ = LeavePolicy.objects.update_or_create(
        leave_type=leave_type,
        employee_kind=employee_kind,
        defaults={
            "annual_entitlement": amount,
            "carry_forward": carry_forward,
            "carry_forward_limit": limit,
            "counting_mode": counting_mode,
            "requires_medical_evidence": requires_medical_evidence,
            "requires_vacation_period": requires_vacation_period,
            "is_active": True,
        },
    )
    return policy


def update_employee_profile(actor, *, user_id, unit_code="", designation="", is_director=False):
    require(actor, "leave_elm.policy.manage")
    person = directory.get_users([user_id]).get(user_id)
    if person is None or person.kind not in {"faculty", "staff"}:
        raise ConflictError(
            "Organizational context can only be set for an active employee.",
            code="employee_not_found",
        )
    profile, _ = EmployeeProfile.objects.update_or_create(
        user_id=user_id,
        defaults={
            "unit_code": unit_code.strip(),
            "designation": designation.strip(),
            "is_director": is_director,
            "updated_by_user_id": actor.user_id,
        },
    )
    return profile


@transaction.atomic
def save_route(
    actor,
    *,
    route_id=None,
    leave_type_code,
    request_kind,
    employee_kind,
    unit_code="",
    designation="",
    director_applicant=False,
    requires_substitute=False,
    steps,
):
    require(actor, "leave_elm.policy.manage")
    try:
        leave_type = LeaveType.objects.get(code=leave_type_code, is_active=True)
    except LeaveType.DoesNotExist as exc:
        raise NotFoundError("Leave category not found.", code="not_found") from exc
    if request_kind not in dict(RouteRule.REQUEST_KINDS):
        raise ConflictError(
            "Unsupported request type for route configuration.", code="invalid_route"
        )
    if employee_kind not in dict(RouteRule.EMPLOYEE_KINDS):
        raise ConflictError(
            "Unsupported employee category for route configuration.", code="invalid_route"
        )
    if not steps:
        raise ConflictError("Configure at least one route step.", code="route_incomplete")
    try:
        route = RouteRule.objects.select_for_update().get(pk=route_id) if route_id else None
    except RouteRule.DoesNotExist as exc:
        raise NotFoundError("Route rule not found.", code="not_found") from exc
    values = {
        "leave_type": leave_type,
        "request_kind": request_kind,
        "employee_kind": employee_kind,
        "unit_code": unit_code.strip(),
        "designation": designation.strip(),
        "director_applicant": director_applicant,
        "requires_substitute": requires_substitute,
        "is_active": True,
        "updated_by_user_id": actor.user_id,
    }
    if route:
        for key, value in values.items():
            setattr(route, key, value)
        route.save()
        route.steps.all().delete()
    else:
        route = RouteRule.objects.create(**values)
    prepared = []
    for index, step in enumerate(steps, start=1):
        assignee_id = int(step["assignee_user_id"])
        person = directory.get_users([assignee_id]).get(assignee_id)
        if person is None or person.kind not in {"faculty", "staff"}:
            raise ConflictError(
                "Every route assignee must be an active employee.", code="route_assignee_invalid"
            )
        prepared.append(
            RouteStep(
                route=route,
                sequence=int(step.get("sequence", index)),
                kind=step["kind"],
                assignee_user_id=assignee_id,
                assignee_role=step.get("assignee_role", "").strip(),
                is_optional=bool(step.get("is_optional", False)),
            )
        )
    prepared.sort(key=lambda step: step.sequence)
    validate_route(route, prepared)
    RouteStep.objects.bulk_create(prepared)
    return route


@transaction.atomic
def create_calendar(actor, *, year, name, weekly_closed_days, dates, vacation_periods):
    require(actor, "leave_elm.calendar.manage")
    year = int(year)
    if year < 2000 or year > 9999:
        raise ConflictError("Calendar year is invalid.", code="invalid_calendar")
    if any(day not in range(7) for day in weekly_closed_days):
        raise ConflictError("Closed weekdays must use values 0 through 6.", code="invalid_calendar")
    calendar = LeaveCalendar.objects.create(
        year=year,
        name=name.strip(),
        weekly_closed_days=sorted(set(weekly_closed_days)),
    )
    date_rows = []
    for item in dates:
        day = item["day"] if isinstance(item["day"], date) else date.fromisoformat(item["day"])
        if day.year != year:
            raise ConflictError(
                "Calendar dates must belong to the calendar year.", code="invalid_calendar"
            )
        if item["kind"] not in dict(CalendarDate.KINDS):
            raise ConflictError("Calendar date kind is invalid.", code="invalid_calendar")
        date_rows.append(
            CalendarDate(
                calendar=calendar,
                day=day,
                kind=item["kind"],
                label=item.get("label", "").strip(),
            )
        )
    CalendarDate.objects.bulk_create(date_rows)
    vacation_rows = []
    for item in vacation_periods:
        start = (
            item["start_date"]
            if isinstance(item["start_date"], date)
            else date.fromisoformat(item["start_date"])
        )
        end = (
            item["end_date"]
            if isinstance(item["end_date"], date)
            else date.fromisoformat(item["end_date"])
        )
        if start.year != year or end.year != year or end < start:
            raise ConflictError(
                "Vacation periods must be valid and belong to this year.", code="invalid_calendar"
            )
        vacation_rows.append(
            VacationPeriod(
                calendar=calendar,
                start_date=start,
                end_date=end,
                label=item.get("label", "").strip(),
                source_reference=item.get("source_reference", "").strip(),
            )
        )
    VacationPeriod.objects.bulk_create(vacation_rows)
    return calendar


@transaction.atomic
def publish_calendar(actor, *, calendar_id):
    require(actor, "leave_elm.calendar.manage")
    try:
        calendar = LeaveCalendar.objects.select_for_update().get(pk=calendar_id)
    except LeaveCalendar.DoesNotExist as exc:
        raise NotFoundError("Calendar not found.", code="not_found") from exc
    if calendar.status != "draft":
        raise ConflictError("Only a draft calendar can be published.", code="calendar_not_draft")
    LeaveCalendar.objects.select_for_update().filter(
        year=calendar.year, status="published"
    ).exclude(pk=calendar.pk).update(status="archived", updated_at=timezone.now())
    calendar.status = "published"
    calendar.published_by_user_id = actor.user_id
    calendar.published_at = timezone.now()
    calendar.save(update_fields=["status", "published_by_user_id", "published_at", "updated_at"])
    record_event_for_calendar(calendar, actor.user_id)
    return calendar


def record_event_for_calendar(calendar, actor_user_id):
    return LeaveConfigurationEvent.objects.create(
        actor_user_id=actor_user_id,
        event="calendar_published",
        object_kind="calendar",
        object_id=calendar.pk,
        details={"year": calendar.year, "name": calendar.name},
    )


@transaction.atomic
def save_sla_policy(
    actor, *, task_kind, reminder_after_hours, escalation_after_hours, escalation_user_id=None
):
    require(actor, "leave_elm.sla.manage")
    if task_kind not in dict(WorkflowTask.KINDS):
        raise ConflictError("Unsupported SLA task kind.", code="invalid_sla")
    reminder = int(reminder_after_hours) if reminder_after_hours is not None else None
    escalation = int(escalation_after_hours) if escalation_after_hours is not None else None
    if (reminder is not None and reminder <= 0) or (escalation is not None and escalation <= 0):
        raise ConflictError("SLA thresholds must be positive hours.", code="invalid_sla")
    if reminder is None and escalation is None:
        raise ConflictError("Configure a reminder or escalation threshold.", code="invalid_sla")
    if reminder is not None and escalation is not None and escalation < reminder:
        raise ConflictError(
            "Escalation cannot occur before the reminder threshold.", code="invalid_sla"
        )
    if escalation is not None and escalation_user_id is None:
        raise ConflictError("Choose an escalation recipient.", code="invalid_sla")
    if escalation_user_id is not None:
        person = directory.get_users([escalation_user_id]).get(escalation_user_id)
        if person is None or person.kind not in {"faculty", "staff"}:
            raise ConflictError(
                "The escalation recipient must be an active employee.", code="invalid_sla"
            )
    SlaPolicy.objects.filter(task_kind=task_kind, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    return SlaPolicy.objects.create(
        task_kind=task_kind,
        reminder_after_hours=reminder,
        escalation_after_hours=escalation,
        escalation_user_id=escalation_user_id,
    )


@transaction.atomic
def record_offline_leave(
    actor,
    *,
    employee_user_id,
    leave_type_code,
    start_date,
    end_date,
    day_part,
    reason,
    station_leave_required,
    station_leave_details,
    medical_evidence_reference,
    sanction_reference,
    sanctioned_by_user_id,
    sanction_date,
):
    require(actor, "leave_elm.offline.record")
    require(actor, "leave_elm.record.manage")
    if not sanction_reference.strip() or not sanctioned_by_user_id or not sanction_date:
        raise ConflictError(
            "Offline sanction reference, authority, and date are required.",
            code="offline_evidence_required",
        )
    if sanction_date > timezone.localdate():
        raise ConflictError(
            "The recorded sanction date cannot be in the future.", code="offline_evidence_invalid"
        )
    authority = directory.get_users([sanctioned_by_user_id]).get(sanctioned_by_user_id)
    if authority is None or authority.kind not in {"faculty", "staff"}:
        raise ConflictError(
            "The offline sanctioning authority must be an active employee.",
            code="offline_authority_invalid",
        )
    person = directory.get_users([employee_user_id]).get(employee_user_id)
    if person is None or person.kind not in {"faculty", "staff"}:
        raise ConflictError(
            "Offline leave can only be recorded for an active employee.", code="employee_not_found"
        )
    try:
        leave_type = LeaveType.objects.get(code=leave_type_code, is_active=True)
    except LeaveType.DoesNotExist as exc:
        raise NotFoundError("Leave category not found.", code="not_found") from exc
    try:
        policy = LeavePolicy.objects.get(
            leave_type=leave_type, employee_kind=person.kind, is_active=True
        )
    except LeavePolicy.DoesNotExist as exc:
        raise ConflictError(
            "No active leave policy applies to this employee.", code="policy_not_configured"
        ) from exc
    calendars = calendar_facts(range(start_date.year, end_date.year + 1))
    try:
        days, by_year = rules.count_and_split(
            leave_type.code, start_date, end_date, day_part, policy.counting_mode, calendars
        )
    except rules.RuleViolation as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    vacation_periods = tuple(
        period for facts in calendars.values() for period in facts.vacation_periods
    )
    if policy.requires_vacation_period and not rules.in_vacation_period(
        start_date, end_date, vacation_periods
    ):
        raise ConflictError(
            "The recorded VL period is outside the configured vacation period.",
            code="outside_vacation_period",
        )
    if station_leave_required and not station_leave_details.strip():
        raise ConflictError(
            "Add the Station Leave details to this record.", code="station_leave_details_required"
        )
    if policy.requires_medical_evidence and not medical_evidence_reference.strip():
        raise ConflictError(
            "Supporting medical evidence is required by policy.", code="medical_evidence_required"
        )
    if rules.has_overlap(
        start_date,
        end_date,
        day_part,
        [
            (app.leave_type.code, app.start_date, app.end_date, app.day_part)
            for app in LeaveApplication.objects.filter(
                employee_user_id=employee_user_id,
                status__in=rules.ACTIVE_APPLICATION_STATES,
            ).select_related("leave_type")
        ],
    ):
        raise ConflictError("The offline record overlaps existing leave.", code="overlap")
    profile = EmployeeProfile.objects.filter(user_id=employee_user_id).first()
    application = LeaveApplication.objects.create(
        employee_user_id=employee_user_id,
        employee_kind=person.kind,
        unit_code=profile.unit_code if profile else "",
        designation=profile.designation if profile else "",
        director_applicant=bool(profile and profile.is_director),
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        day_part=day_part,
        days=days,
        reason=reason.strip(),
        station_leave_required=station_leave_required,
        station_leave_details=station_leave_details.strip(),
        medical_evidence_reference=medical_evidence_reference.strip(),
        substitute_required=False,
        status="approved",
        submitted_at=timezone.now(),
        approved_at=timezone.now(),
        approved_by_user_id=sanctioned_by_user_id,
        origin="offline",
        offline_reference=sanction_reference.strip(),
        offline_sanctioned_by_user_id=sanctioned_by_user_id,
        offline_sanction_date=sanction_date,
    )
    accounts.reserve(
        subject=application,
        subject_field="application",
        employee_user_id=employee_user_id,
        employee_kind=person.kind,
        leave_type=leave_type,
        by_year=by_year,
        actor_user_id=actor.user_id,
    )
    accounts.post_reservations(
        subject=application, subject_field="application", actor_user_id=actor.user_id
    )

    record_event(
        subject=application,
        actor_user_id=actor.user_id,
        event="offline_synchronized",
        to_status="approved",
        details={
            "sanction_reference": sanction_reference.strip(),
            "sanctioned_by_user_id": sanctioned_by_user_id,
            "sanction_date": sanction_date.isoformat(),
        },
    )
    return application


@transaction.atomic
def adjust_balance(actor, *, balance_id, amount, reason):
    require(actor, "leave_elm.record.manage")
    if not reason.strip():
        raise ConflictError(
            "A reason is required for an account correction.", code="reason_required"
        )
    try:
        balance = LeaveBalance.objects.select_for_update().get(pk=balance_id)
    except LeaveBalance.DoesNotExist as exc:
        raise NotFoundError("Leave balance not found.", code="not_found") from exc
    delta = Decimal(amount)
    new_available = balance.available + delta
    if new_available < 0:
        raise ConflictError(
            "The correction cannot make the available balance negative.", code="invalid_adjustment"
        )
    balance.adjustments += delta
    balance.save(update_fields=["adjustments", "updated_at"])
    LeaveLedgerEntry.objects.create(
        balance=balance,
        amount=delta,
        kind="adjustment",
        actor_user_id=actor.user_id,
        source_kind="maintenance",
        source_id=balance.pk,
        reason=reason.strip()[:500],
        idempotency_key=f"adjustment:{balance.pk}:{balance.updated_at.timestamp()}",
    )
    return balance


def list_policies(actor):
    require(actor, "leave_elm.policy.manage")
    return LeavePolicy.objects.select_related("leave_type").order_by(
        "leave_type__code", "employee_kind"
    )


def list_routes(actor):
    require(actor, "leave_elm.policy.manage")
    return (
        RouteRule.objects.select_related("leave_type")
        .prefetch_related("steps")
        .order_by("leave_type__code", "request_kind", "employee_kind")
    )


def list_calendars(actor):
    require(actor, "leave_elm.calendar.manage")
    return LeaveCalendar.objects.prefetch_related("dates", "vacation_periods").order_by(
        "-year", "-created_at"
    )


def list_sla_policies(actor):
    require(actor, "leave_elm.sla.manage")
    return SlaPolicy.objects.filter(is_active=True).order_by("task_kind")


def update_employee_profile_record(
    actor, *, user_id, unit_code="", designation="", is_director=False
):
    return update_employee_profile(
        actor,
        user_id=user_id,
        unit_code=unit_code,
        designation=designation,
        is_director=is_director,
    )
