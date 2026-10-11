"""Leave request and workflow services. All writes lock state and preserve an audit trail."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.api.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from modules.directory import contracts as directory
from modules.elm.domain import leave_rules as rules
from modules.elm.models import (
    LeaveActionRequest,
    LeaveApplication,
    LeavePolicy,
    LeaveReservation,
    LeaveType,
    SubstituteRequest,
    WorkflowTask,
)
from modules.elm.selectors import leave as selectors
from modules.elm.services import accounts
from modules.elm.services.workflow import (
    activate_next,
    calendar_facts,
    cancel_subject_tasks,
    create_route_tasks,
    create_substitute_task,
    employee_context,
    notify,
    record_event,
    require,
    resolve_route,
    visible_action,
    visible_application,
    visible_task,
)

ZERO = Decimal("0.00")
ACTIVE_STATES = tuple(rules.ACTIVE_APPLICATION_STATES)


def _route_requires_substitute(route):
    return route.requires_substitute


def _validate_substitute(*, nominee_user_id, employee_user_id, start, end):
    if nominee_user_id == employee_user_id:
        raise ConflictError(
            "The applicant cannot be their own substitute.", code="invalid_substitute"
        )
    person = directory.get_users([nominee_user_id]).get(nominee_user_id)
    if person is None or person.kind not in {"faculty", "staff"}:
        raise ConflictError(
            "The substitute must be another active employee.", code="invalid_substitute"
        )
    existing = LeaveApplication.objects.filter(
        employee_user_id=nominee_user_id,
        status__in=ACTIVE_STATES,
        start_date__lte=end,
        end_date__gte=start,
    ).exists()
    if existing:
        raise ConflictError(
            "The substitute has overlapping pending or approved leave.",
            code="substitute_unavailable",
        )


def _calendar_years(start, end):
    return range(start.year, end.year + 1)


def _policy_for(leave_type, employee_kind):
    try:
        return LeavePolicy.objects.select_related("leave_type").get(
            leave_type=leave_type, employee_kind=employee_kind, is_active=True
        )
    except LeavePolicy.DoesNotExist as exc:
        raise ConflictError(
            "No active leave policy applies to this employee.", code="policy_not_configured"
        ) from exc


def _validate_period(
    *, policy, leave_type, start, end, day_part, calendars, medical_evidence_reference=""
):
    if policy.requires_medical_evidence and not medical_evidence_reference.strip():
        raise ConflictError(
            "Supporting medical evidence is required by the current policy.",
            code="medical_evidence_required",
        )
    try:
        total, by_year = rules.count_and_split(
            leave_type.code, start, end, day_part, policy.counting_mode, calendars
        )
    except rules.RuleViolation as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    vacation_periods = tuple(
        period for facts in calendars.values() for period in facts.vacation_periods
    )
    if policy.requires_vacation_period and not rules.in_vacation_period(
        start, end, vacation_periods
    ):
        raise ConflictError(
            "The requested period is outside the configured vacation period.",
            code="outside_vacation_period",
        )
    return total, by_year


def _overlap_rows(employee_user_id, *, exclude_application_id=None):
    qs = LeaveApplication.objects.filter(
        employee_user_id=employee_user_id,
        status__in=ACTIVE_STATES,
    )
    if exclude_application_id is not None:
        qs = qs.exclude(pk=exclude_application_id)
    return [
        (app.leave_type.code, app.start_date, app.end_date, app.day_part)
        for app in qs.select_related("leave_type")
    ]


def _assert_no_overlap(
    *, employee_user_id, leave_type, start, end, day_part, exclude_application_id=None
):
    if rules.has_overlap(
        start,
        end,
        day_part,
        _overlap_rows(employee_user_id, exclude_application_id=exclude_application_id),
    ):
        raise ConflictError(
            "These dates overlap another pending or approved leave request.", code="overlap"
        )


def _make_substitute(*, subject, route, employee_user_id, nominee_user_id, start, end):
    if route.requires_substitute and nominee_user_id is None:
        raise ConflictError(
            "A substitute is required by the configured route.", code="substitute_required"
        )
    if not route.requires_substitute and nominee_user_id is not None:
        raise ConflictError(
            "This route does not require substitute coverage.", code="substitute_not_required"
        )
    if not route.requires_substitute:
        return None
    _validate_substitute(
        nominee_user_id=nominee_user_id, employee_user_id=employee_user_id, start=start, end=end
    )
    request = SubstituteRequest.objects.create(
        **(
            {"application": subject}
            if isinstance(subject, LeaveApplication)
            else {"action_request": subject}
        ),
        nominee_user_id=nominee_user_id,
        responsibility_start=start,
        responsibility_end=end,
    )
    create_substitute_task(subject=subject, substitute_request=request)
    return request


@transaction.atomic
def apply_for_leave(
    actor,
    *,
    leave_type_id: int,
    start_date: date,
    end_date: date,
    reason: str,
    day_part: str = "full",
    station_leave_required: bool = False,
    station_leave_details: str = "",
    medical_evidence_reference: str = "",
    substitute_user_id: int | None = None,
):
    require(actor, "leave_elm.application.apply")
    employee = employee_context(actor)
    if not reason.strip():
        raise ConflictError("A purpose or reason is required.", code="reason_required")
    if station_leave_required and not station_leave_details.strip():
        raise ConflictError(
            "Add the Station Leave details to this application.",
            code="station_leave_details_required",
        )
    try:
        leave_type = LeaveType.objects.get(pk=leave_type_id, is_active=True)
    except LeaveType.DoesNotExist as exc:
        raise NotFoundError("Leave category not found.", code="not_found") from exc
    policy = _policy_for(leave_type, employee["employee_kind"])
    calendars = calendar_facts(_calendar_years(start_date, end_date))
    days, by_year = _validate_period(
        policy=policy,
        leave_type=leave_type,
        start=start_date,
        end=end_date,
        day_part=day_part,
        calendars=calendars,
        medical_evidence_reference=medical_evidence_reference,
    )
    _assert_no_overlap(
        employee_user_id=actor.user_id,
        leave_type=leave_type,
        start=start_date,
        end=end_date,
        day_part=day_part,
    )
    route, steps = resolve_route(leave_type=leave_type, request_kind="leave", employee=employee)
    if route.requires_substitute and substitute_user_id is None:
        raise ConflictError(
            "A substitute is required by the configured route.", code="substitute_required"
        )
    if not route.requires_substitute and substitute_user_id is not None:
        raise ConflictError(
            "This route does not require substitute coverage.", code="substitute_not_required"
        )

    application = LeaveApplication.objects.create(
        employee_user_id=actor.user_id,
        employee_kind=employee["employee_kind"],
        unit_code=employee["unit_code"],
        designation=employee["designation"],
        director_applicant=employee["director_applicant"],
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        day_part=day_part,
        days=days,
        reason=reason.strip(),
        station_leave_required=station_leave_required,
        station_leave_details=station_leave_details.strip(),
        medical_evidence_reference=medical_evidence_reference.strip(),
        substitute_required=route.requires_substitute,
        status="awaiting_substitute" if route.requires_substitute else "pending_approval",
        submitted_at=timezone.now(),
    )
    accounts.reserve(
        subject=application,
        subject_field="application",
        employee_user_id=actor.user_id,
        employee_kind=employee["employee_kind"],
        leave_type=leave_type,
        by_year=by_year,
        actor_user_id=actor.user_id,
    )
    if route.requires_substitute:
        _make_substitute(
            subject=application,
            route=route,
            employee_user_id=actor.user_id,
            nominee_user_id=substitute_user_id,
            start=start_date,
            end=end_date,
        )
    else:
        create_route_tasks(subject=application, steps=steps)
    record_event(
        subject=application,
        actor_user_id=actor.user_id,
        event="submitted",
        to_status=application.status,
        details={"days": str(days), "leave_type": leave_type.code},
    )
    return application


@transaction.atomic
def replace_substitute(actor, *, application_id: int, nominee_user_id: int):
    require(actor, "leave_elm.application.apply")
    application = visible_application(actor, application_id, for_update=True)
    if application.status != "applicant_action_required" or not application.substitute_required:
        raise ConflictError(
            "This application is not waiting for a replacement substitute.",
            code="not_waiting_for_substitute",
        )
    route, _steps = resolve_route(
        leave_type=application.leave_type,
        request_kind="leave",
        employee={
            "employee_kind": application.employee_kind,
            "unit_code": application.unit_code,
            "designation": application.designation,
            "director_applicant": application.director_applicant,
        },
    )
    if not route.requires_substitute:
        raise ConflictError(
            "The configured route no longer requires substitute coverage.",
            code="substitute_not_required",
        )
    SubstituteRequest.objects.filter(application=application, status="pending").update(
        status="superseded", updated_at=timezone.now()
    )
    application.status = "awaiting_substitute"
    application.save(update_fields=["status", "updated_at"])
    _make_substitute(
        subject=application,
        route=route,
        employee_user_id=application.employee_user_id,
        nominee_user_id=nominee_user_id,
        start=application.start_date,
        end=application.end_date,
    )
    record_event(
        subject=application,
        actor_user_id=actor.user_id,
        event="substitute_replaced",
        from_status="applicant_action_required",
        to_status=application.status,
        details={"nominee_user_id": nominee_user_id},
    )
    return application


@transaction.atomic
def replace_action_substitute(actor, *, action_id: int, nominee_user_id: int):
    require(actor, "leave_elm.application.apply")
    action = visible_action(actor, action_id, for_update=True)
    if action.kind != "extension" or action.status != "applicant_action_required":
        raise ConflictError(
            "This extension is not waiting for a replacement substitute.",
            code="not_waiting_for_substitute",
        )
    application = action.application
    route, _ = resolve_route(
        leave_type=application.leave_type,
        request_kind="extension",
        employee={
            "employee_kind": application.employee_kind,
            "unit_code": application.unit_code,
            "designation": application.designation,
            "director_applicant": application.director_applicant,
        },
    )
    if not route.requires_substitute:
        raise ConflictError(
            "The configured extension route no longer requires a substitute.",
            code="substitute_not_required",
        )
    SubstituteRequest.objects.filter(action_request=action, status="pending").update(
        status="superseded", updated_at=timezone.now()
    )
    action.status = "awaiting_substitute"
    action.save(update_fields=["status", "updated_at"])
    _make_substitute(
        subject=action,
        route=route,
        employee_user_id=application.employee_user_id,
        nominee_user_id=nominee_user_id,
        start=application.end_date + timedelta(days=1),
        end=action.requested_end_date,
    )
    record_event(
        subject=action,
        actor_user_id=actor.user_id,
        event="substitute_replaced",
        from_status="applicant_action_required",
        to_status=action.status,
        details={"nominee_user_id": nominee_user_id},
    )
    return action


@transaction.atomic
def respond_to_substitute(actor, *, task_id: int, accept: bool, note: str = ""):
    require(actor, "leave_elm.substitute.respond")
    task = visible_task(actor, task_id, for_update=True)
    if task.kind != "substitute" or task.status != "pending":
        raise ConflictError(
            "This substitute request is no longer pending.", code="task_not_pending"
        )
    request = (
        SubstituteRequest.objects.select_for_update()
        .filter(
            nominee_user_id=actor.user_id,
            status="pending",
            **(
                {"application": task.application}
                if task.application_id
                else {"action_request": task.action_request}
            ),
        )
        .first()
    )
    if request is None:
        raise NotFoundError("Substitute request not found.", code="not_found")
    subject = task.application or task.action_request
    if subject.status != "awaiting_substitute":
        raise ConflictError(
            "This substitute request is no longer awaiting a response.", code="task_not_pending"
        )
    task.status = "completed"
    task.result = "accept" if accept else "decline"
    task.note = note.strip()
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "result", "note", "completed_at", "updated_at"])
    request.status = "accepted" if accept else "declined"
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at", "updated_at"])
    before = subject.status
    subject.status = "pending_approval" if accept else "applicant_action_required"
    subject.save(update_fields=["status", "updated_at"])
    if accept:
        _, steps = resolve_route(
            leave_type=subject.leave_type
            if isinstance(subject, LeaveApplication)
            else subject.application.leave_type,
            request_kind="leave" if isinstance(subject, LeaveApplication) else subject.kind,
            employee={
                "employee_kind": subject.employee_kind
                if isinstance(subject, LeaveApplication)
                else subject.application.employee_kind,
                "unit_code": subject.unit_code
                if isinstance(subject, LeaveApplication)
                else subject.application.unit_code,
                "designation": subject.designation
                if isinstance(subject, LeaveApplication)
                else subject.application.designation,
                "director_applicant": subject.director_applicant
                if isinstance(subject, LeaveApplication)
                else subject.application.director_applicant,
            },
        )
        create_route_tasks(subject=subject, steps=steps)
    else:
        employee_user_id = (
            subject.employee_user_id
            if isinstance(subject, LeaveApplication)
            else subject.application.employee_user_id
        )
        notify(
            employee_user_id,
            "substitute_declined",
            "Choose another substitute",
            "Your nominated substitute declined. Nominate another eligible employee or withdraw.",
        )
    record_event(
        subject=subject,
        actor_user_id=actor.user_id,
        event="substitute_accepted" if accept else "substitute_declined",
        from_status=before,
        to_status=subject.status,
        details={"substitute_user_id": actor.user_id},
    )
    return task


@transaction.atomic
def withdraw_application(actor, *, application_id: int):
    require(actor, "leave_elm.application.apply")
    application = visible_application(actor, application_id, for_update=True)
    if not rules.may_withdraw(application.status):
        raise ConflictError(
            "Only a pending request may be withdrawn before final approval.",
            code="not_withdrawable",
        )
    before = application.status
    accounts.release_reservations(
        subject=application,
        subject_field="application",
        actor_user_id=actor.user_id,
        reason="Employee withdrew pending leave",
    )
    cancel_subject_tasks(subject=application)
    application.status = "withdrawn"
    application.save(update_fields=["status", "updated_at"])
    SubstituteRequest.objects.filter(application=application, status="pending").update(
        status="superseded", updated_at=timezone.now()
    )
    record_event(
        subject=application,
        actor_user_id=actor.user_id,
        event="withdrawn",
        from_status=before,
        to_status=application.status,
    )
    for task in WorkflowTask.objects.filter(application=application, status="cancelled"):
        notify(
            task.assignee_user_id,
            "request_withdrawn",
            "Leave request withdrawn",
            "The employee withdrew this request; the assigned task is no longer actionable.",
            task,
        )
    return application


@transaction.atomic
def request_leave_action(
    actor,
    *,
    application_id: int,
    kind: str,
    reason: str = "",
    requested_end_date: date | None = None,
    actual_resumption_date: date | None = None,
    substitute_user_id: int | None = None,
    medical_evidence_reference: str = "",
):
    require(actor, "leave_elm.application.apply")
    application = visible_application(actor, application_id, for_update=True)
    if application.status != "approved":
        raise ConflictError(
            "Only approved leave can be changed through a new action request.",
            code="application_not_approved",
        )
    if kind not in {"cancellation", "extension", "resumption"}:
        raise ConflictError("Choose cancellation, extension, or resumption.", code="invalid_action")
    if application.actions.filter(
        kind=kind,
        status__in=["awaiting_substitute", "applicant_action_required", "pending_approval"],
    ).exists():
        raise ConflictError(
            "A request of this kind is already pending.", code="action_already_pending"
        )
    today = timezone.localdate()
    employee = {
        "employee_kind": application.employee_kind,
        "unit_code": application.unit_code,
        "designation": application.designation,
        "director_applicant": application.director_applicant,
    }
    action_days = ZERO
    by_year = {}
    if kind == "cancellation":
        if not rules.may_cancel_approved(application.status, application.start_date, today):
            raise ConflictError(
                "Approved leave can only be cancelled before its start date.",
                code="not_cancellable",
            )
        if not reason.strip():
            raise ConflictError(
                "A reason is required for a cancellation request.", code="reason_required"
            )
    elif kind == "extension":
        if not rules.may_extend(
            application.leave_type.code,
            application.status,
            application.start_date,
            application.end_date,
            today,
        ):
            raise ConflictError(
                "Only ongoing EL, COL, or VL may be extended.", code="not_extendable"
            )
        if requested_end_date is None or requested_end_date <= application.end_date:
            raise ConflictError(
                "The extension end date must be after the approved end date.",
                code="invalid_extension",
            )
        if not reason.strip():
            raise ConflictError(
                "A reason is required for an extension request.", code="reason_required"
            )
        policy = _policy_for(application.leave_type, application.employee_kind)
        calendars = calendar_facts(
            _calendar_years(application.end_date + timedelta(days=1), requested_end_date)
        )
        action_days, by_year = _validate_period(
            policy=policy,
            leave_type=application.leave_type,
            start=application.end_date + timedelta(days=1),
            end=requested_end_date,
            day_part="full",
            calendars=calendars,
            medical_evidence_reference=medical_evidence_reference,
        )
        _assert_no_overlap(
            employee_user_id=actor.user_id,
            leave_type=application.leave_type,
            start=application.end_date + timedelta(days=1),
            end=requested_end_date,
            day_part="full",
            exclude_application_id=application.pk,
        )
    else:
        if not rules.may_resume(application.leave_type.code, application.status):
            raise ConflictError(
                "Formal resumption applies to approved EL, COL, and VL.", code="not_resumable"
            )
        if actual_resumption_date is None or actual_resumption_date < application.start_date:
            raise ConflictError(
                "Enter an actual resumption date on or after leave start.",
                code="invalid_resumption_date",
            )
        if actual_resumption_date > today:
            raise ConflictError(
                "An actual resumption date cannot be in the future.", code="invalid_resumption_date"
            )
        if not reason.strip():
            raise ConflictError("A note is required for resumption review.", code="reason_required")

    route, steps = resolve_route(
        leave_type=application.leave_type, request_kind=kind, employee=employee
    )
    if kind != "extension" and route.requires_substitute:
        raise ConflictError(
            "Only extension routes may require substitute coverage.", code="substitute_not_required"
        )
    if kind == "extension" and route.requires_substitute and substitute_user_id is None:
        raise ConflictError(
            "A substitute is required by the configured route.", code="substitute_required"
        )
    if kind != "extension" and substitute_user_id is not None:
        raise ConflictError(
            "Only an extension route may require a substitute.", code="substitute_not_required"
        )
    if kind == "extension" and not route.requires_substitute and substitute_user_id is not None:
        raise ConflictError(
            "This route does not require substitute coverage.", code="substitute_not_required"
        )

    action = LeaveActionRequest.objects.create(
        application=application,
        kind=kind,
        requested_end_date=requested_end_date,
        actual_resumption_date=actual_resumption_date,
        days=action_days,
        reason=reason.strip(),
        medical_evidence_reference=medical_evidence_reference.strip(),
        status="awaiting_substitute" if route.requires_substitute else "pending_approval",
        submitted_by_user_id=actor.user_id,
        submitted_at=timezone.now(),
    )
    if kind == "extension":
        accounts.reserve(
            subject=action,
            subject_field="action_request",
            employee_user_id=application.employee_user_id,
            employee_kind=application.employee_kind,
            leave_type=application.leave_type,
            by_year=by_year,
            actor_user_id=actor.user_id,
        )
    if route.requires_substitute:
        _make_substitute(
            subject=action,
            route=route,
            employee_user_id=application.employee_user_id,
            nominee_user_id=substitute_user_id,
            start=application.end_date + timedelta(days=1),
            end=requested_end_date,
        )
    else:
        create_route_tasks(subject=action, steps=steps)
    if kind == "cancellation":
        application.status = "cancellation_pending"
        application.save(update_fields=["status", "updated_at"])
    record_event(
        subject=action,
        actor_user_id=actor.user_id,
        event=f"{kind}_submitted",
        to_status=action.status,
        details={"application_id": application.pk},
    )
    return action


@transaction.atomic
def withdraw_action(actor, *, action_id: int):
    require(actor, "leave_elm.application.apply")
    action = visible_action(actor, action_id, for_update=True)
    if action.status not in {
        "awaiting_substitute",
        "applicant_action_required",
        "pending_approval",
    }:
        raise ConflictError(
            "Only a pending leave action may be withdrawn.", code="not_withdrawable"
        )
    before = action.status
    accounts.release_reservations(
        subject=action,
        subject_field="action_request",
        actor_user_id=actor.user_id,
        reason="Employee withdrew pending leave action",
    )
    cancel_subject_tasks(subject=action)
    action.status = "withdrawn"
    action.save(update_fields=["status", "updated_at"])
    if action.kind == "cancellation":
        action.application.status = "approved"
        action.application.save(update_fields=["status", "updated_at"])
    record_event(
        subject=action,
        actor_user_id=actor.user_id,
        event="withdrawn",
        from_status=before,
        to_status=action.status,
    )
    return action


def _subject_from_task(task):
    return task.application or task.action_request


def _set_subject_status(subject, status):
    subject.status = status
    subject.save(update_fields=["status", "updated_at"])


def _finalize_approval(*, subject, actor):
    if isinstance(subject, LeaveApplication):
        accounts.post_reservations(
            subject=subject, subject_field="application", actor_user_id=actor.user_id
        )
        subject.status = "approved"
        subject.approved_at = timezone.now()
        subject.approved_by_user_id = actor.user_id
        subject.save(update_fields=["status", "approved_at", "approved_by_user_id", "updated_at"])
        return
    action = subject
    application = LeaveApplication.objects.select_for_update().get(pk=action.application_id)
    if action.kind == "cancellation":
        accounts.reverse_application_usage(
            application=application,
            actor_user_id=actor.user_id,
            reason="Approved cancellation of leave before start",
        )
        application.status = "cancelled"
        application.save(update_fields=["status", "updated_at"])
    elif action.kind == "extension":
        accounts.post_reservations(
            subject=action, subject_field="action_request", actor_user_id=actor.user_id
        )
        # Once approved, extension reservations become part of the application
        # ledger so later resumption adjustments include the extended period.
        LeaveReservation.objects.filter(action_request=action, status="posted").update(
            application=application, action_request=None
        )
        application.end_date = action.requested_end_date
        application.days += action.days
        application.save(update_fields=["end_date", "days", "updated_at"])
    elif action.kind == "resumption":
        facts = calendar_facts(
            _calendar_years(application.start_date, action.actual_resumption_date)
        )
        policy = _policy_for(application.leave_type, application.employee_kind)
        try:
            # Resumption records the actual interval, including a late return
            # that may extend beyond the approved vacation window.
            new_days, new_years = rules.count_and_split(
                application.leave_type.code,
                application.start_date,
                action.actual_resumption_date,
                "full",
                policy.counting_mode,
                facts,
            )
        except rules.RuleViolation as exc:
            raise ConflictError(exc.message, code=exc.code) from exc
        posted = list(
            application.reservations.filter(status="posted")
            .select_related("balance")
            .order_by("balance__year", "id")
        )
        old_years = defaultdict(lambda: ZERO)
        reservations_by_year = defaultdict(list)
        for reservation in posted:
            year = reservation.balance.year
            old_years[year] += reservation.days
            reservations_by_year[year].append(reservation)
        delta = {
            year: new_years.get(year, ZERO) - old_years.get(year, ZERO)
            for year in set(old_years) | set(new_years)
        }
        accounts.adjust_used(
            employee_user_id=application.employee_user_id,
            leave_type=application.leave_type,
            employee_kind=application.employee_kind,
            by_year=delta,
            actor_user_id=actor.user_id,
            source_kind="resumption",
            source_id=action.pk,
            reason="Resumption review adjusted actual leave period",
        )
        # Keep application reservations aligned with corrected usage; later
        # cancellation and resumption calculations depend on these rows.
        for year in set(old_years) | set(new_years):
            rows = reservations_by_year.get(year, [])
            desired = new_years.get(year, ZERO)
            if desired <= ZERO:
                for reservation in rows:
                    reservation.status = "released"
                    reservation.save(update_fields=["status", "updated_at"])
            elif rows:
                keeper, *duplicates = rows
                keeper.days = desired
                keeper.save(update_fields=["days", "updated_at"])
                for reservation in duplicates:
                    reservation.status = "released"
                    reservation.save(update_fields=["status", "updated_at"])
            else:
                balance, _ = accounts.account_for(
                    employee_user_id=application.employee_user_id,
                    leave_type=application.leave_type,
                    employee_kind=application.employee_kind,
                    year=year,
                    for_update=True,
                )
                LeaveReservation.objects.create(
                    application=application, balance=balance, days=desired, status="posted"
                )
        application.end_date = action.actual_resumption_date
        application.days = new_days
        application.save(update_fields=["end_date", "days", "updated_at"])
    action.status = "approved"
    action.save(update_fields=["status", "updated_at"])


def _finalize_rejection(*, subject, actor):
    if isinstance(subject, LeaveApplication):
        accounts.release_reservations(
            subject=subject,
            subject_field="application",
            actor_user_id=actor.user_id,
            reason="Leave request rejected",
        )
        _set_subject_status(subject, "rejected")
        return
    action = subject
    accounts.release_reservations(
        subject=action,
        subject_field="action_request",
        actor_user_id=actor.user_id,
        reason="Leave action request rejected",
    )
    action.status = "rejected"
    action.save(update_fields=["status", "updated_at"])
    if action.kind == "cancellation":
        action.application.status = "approved"
        action.application.save(update_fields=["status", "updated_at"])


@transaction.atomic
def decide_task(actor, *, task_id: int, decision: str, note: str = ""):
    require(actor, "leave_elm.workflow.act")
    task = visible_task(actor, task_id, for_update=True)
    if task.status != "pending" or task.kind == "substitute":
        raise ConflictError(
            "This workflow task is not awaiting an approval decision.", code="task_not_pending"
        )
    subject = _subject_from_task(task)
    owner_id = (
        subject.employee_user_id
        if isinstance(subject, LeaveApplication)
        else subject.application.employee_user_id
    )
    if owner_id == actor.user_id and task.kind != "self_sanction":
        raise PermissionDeniedError(
            "You cannot review your own leave request.", code="self_approval"
        )
    allowed = {
        "unit_head_final": {"approve", "reject"},
        "unit_head_recommendation": {"recommend", "not_recommend"},
        "establishment": {"forward"},
        "sanctioning_authority": {"approve", "reject"},
        "self_sanction": {"approve", "reject"},
        "resumption_review": {"approve", "reject"},
    }.get(task.kind, set())
    if decision not in allowed:
        raise ConflictError(
            "This action is not valid for the assigned workflow step.", code="invalid_task_decision"
        )
    if decision == "reject" and not note.strip():
        raise ConflictError(
            "A reason is required when rejecting a request.", code="reason_required"
        )

    before = subject.status
    task.status = "completed"
    task.result = decision
    task.note = note.strip()
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "result", "note", "completed_at", "updated_at"])

    final = task.kind in {
        "unit_head_final",
        "sanctioning_authority",
        "self_sanction",
        "resumption_review",
    }
    if decision == "reject" and final:
        _finalize_rejection(subject=subject, actor=actor)
        cancel_subject_tasks(subject=subject)
        if task.application_id:
            notify(
                task.application.employee_user_id,
                "request_rejected",
                "Leave request rejected",
                note.strip(),
                task,
            )
        else:
            notify(
                task.action_request.submitted_by_user_id,
                "request_rejected",
                "Leave action request rejected",
                note.strip(),
                task,
            )
    elif decision == "approve" and final:
        _finalize_approval(subject=subject, actor=actor)
        cancel_subject_tasks(subject=subject)
        employee_user_id = (
            subject.employee_user_id
            if isinstance(subject, LeaveApplication)
            else subject.application.employee_user_id
        )
        notify(
            employee_user_id,
            "request_approved",
            "Leave request approved",
            "Your leave request was approved.",
            task,
        )
    else:
        next_task = activate_next(subject=subject)
        if next_task is None:
            raise ConflictError(
                "The configured route ended without a final authority.", code="route_incomplete"
            )

    record_event(
        subject=subject,
        actor_user_id=actor.user_id,
        event=f"task_{decision}",
        from_status=before,
        to_status=subject.status,
        details={"task_id": task.pk, "task_kind": task.kind, "note": note.strip()},
    )
    return task


def mark_notification_read(actor, notification_id: int):
    require(actor, "leave_elm.application.view")
    from modules.elm.models import ElmNotification

    try:
        item = ElmNotification.objects.get(pk=notification_id, recipient_user_id=actor.user_id)
    except ElmNotification.DoesNotExist as exc:
        raise NotFoundError("Notification not found.", code="not_found") from exc
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at", "updated_at"])
    return item


def my_balances(actor):
    require(actor, "leave_elm.balance.view")
    return selectors.balances(actor)


def my_history(actor):
    require(actor, "leave_elm.balance.view")
    return selectors.ledger_entries(actor)
