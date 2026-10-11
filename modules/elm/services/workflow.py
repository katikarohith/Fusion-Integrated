"""Shared route, calendar, notification and workflow-task helpers."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.api.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from modules.elm.domain.leave_rules import CalendarFacts
from modules.elm.models import (
    CalendarDate,
    ElmNotification,
    EmployeeProfile,
    LeaveActionRequest,
    LeaveApplication,
    LeaveCalendar,
    RouteRule,
    RouteStep,
    SlaPolicy,
    VacationPeriod,
    WorkflowEvent,
    WorkflowTask,
)


def require(actor, permission: str) -> None:
    if actor is None or not actor.has_permission(permission):
        raise PermissionDeniedError(
            "This action requires " + permission + ".", code="permission_denied"
        )


def employee_context(actor):
    if actor.kind not in {"faculty", "staff"}:
        raise PermissionDeniedError(
            "ELM leave activity is available to faculty and staff.", code="employee_only"
        )
    profile = EmployeeProfile.objects.filter(user_id=actor.user_id).first()
    return {
        "employee_kind": actor.kind,
        "unit_code": profile.unit_code if profile else "",
        "designation": profile.designation if profile else "",
        "director_applicant": bool(profile and profile.is_director),
    }


def calendar_facts(years) -> dict[int, CalendarFacts]:
    facts = {}
    for year in sorted(set(years)):
        calendar = LeaveCalendar.objects.filter(year=year, status="published").first()
        if calendar is None:
            raise ConflictError(
                f"No published leave calendar is configured for {year}.",
                code="calendar_unavailable",
            )
        dates = list(CalendarDate.objects.filter(calendar=calendar))
        vacations = list(VacationPeriod.objects.filter(calendar=calendar))
        facts[year] = CalendarFacts(
            closed_dates=frozenset(d.day for d in dates if d.kind == "closed"),
            restricted_holidays=frozenset(d.day for d in dates if d.kind == "restricted_holiday"),
            closed_weekdays=frozenset(calendar.weekly_closed_days),
            vacation_periods=tuple((p.start_date, p.end_date) for p in vacations),
        )
    return facts


def resolve_route(*, leave_type, request_kind, employee):
    routes = list(
        RouteRule.objects.filter(
            leave_type=leave_type,
            request_kind=request_kind,
            employee_kind=employee["employee_kind"],
            director_applicant=employee["director_applicant"],
            is_active=True,
        )
        .filter(Q(unit_code=employee["unit_code"]) | Q(unit_code=""))
        .filter(Q(designation=employee["designation"]) | Q(designation=""))
        .prefetch_related("steps")
    )
    if not routes:
        raise ConflictError(
            "No approval route is configured for this employee and request.",
            code="route_not_configured",
        )

    def specificity(route):
        return int(bool(route.unit_code)) + int(bool(route.designation))

    best = max(specificity(route) for route in routes)
    matches = [route for route in routes if specificity(route) == best]
    if len(matches) != 1:
        raise ConflictError(
            "More than one approval route matches this employee context.", code="route_ambiguous"
        )
    route = matches[0]
    steps = list(route.steps.all())
    if not steps:
        raise ConflictError("The configured approval route has no steps.", code="route_incomplete")
    validate_route(route, steps)
    return route, steps


def validate_route(route: RouteRule, steps: list[RouteStep]) -> None:
    if (
        not steps
        or any(step.sequence < 1 for step in steps)
        or len({step.sequence for step in steps}) != len(steps)
    ):
        raise ConflictError(
            "Route steps need unique positive sequence numbers.", code="route_invalid"
        )
    steps = sorted(steps, key=lambda step: step.sequence)
    kinds = [step.kind for step in steps]
    last = kinds[-1]
    if route.request_kind == "resumption":
        valid = last == "resumption_review" and len(kinds) == 1
    elif route.request_kind == "leave" and route.director_applicant:
        valid = kinds == ["self_sanction"]
    elif route.leave_type.code in {"CL", "RH"}:
        valid = last == "unit_head_final" and kinds == ["unit_head_final"]
    else:
        valid = (
            kinds[0] == "unit_head_recommendation"
            and last == "sanctioning_authority"
            and all(
                kind in {"unit_head_recommendation", "establishment", "sanctioning_authority"}
                for kind in kinds
            )
            and kinds.count("unit_head_recommendation") == 1
            and kinds.count("sanctioning_authority") == 1
        )
    if not valid:
        raise ConflictError(
            "The configured route does not match the leave authority rules.", code="route_invalid"
        )


def _task_deadline(kind: str):
    policy = SlaPolicy.objects.filter(task_kind=kind, is_active=True).first()
    if policy and policy.reminder_after_hours is not None:
        return timezone.now() + timedelta(hours=policy.reminder_after_hours)
    return None


def notify(recipient_user_id: int, kind: str, title: str, body: str, task=None):
    return ElmNotification.objects.create(
        recipient_user_id=recipient_user_id,
        kind=kind,
        title=title[:180],
        body=body[:500],
        task=task,
    )


def _subject_kwargs(subject):
    if isinstance(subject, LeaveApplication):
        return {"application": subject, "action_request": None}
    if isinstance(subject, LeaveActionRequest):
        return {"application": None, "action_request": subject}
    raise TypeError("Unsupported ELM workflow subject.")


@transaction.atomic
def create_route_tasks(*, subject, steps: list[RouteStep]):
    kwargs = _subject_kwargs(subject)
    for step in steps:
        WorkflowTask.objects.create(
            **kwargs,
            kind=step.kind,
            sequence=step.sequence,
            assignee_user_id=step.assignee_user_id,
            assignee_role=step.assignee_role,
            status="queued",
        )
    activate_next(subject=subject)
    return subject


@transaction.atomic
def create_substitute_task(*, subject, substitute_request):
    kwargs = _subject_kwargs(subject)
    task = WorkflowTask.objects.create(
        **kwargs,
        kind="substitute",
        sequence=0,
        assignee_user_id=substitute_request.nominee_user_id,
        assignee_role="Substitute / Responsibility Holder",
        status="pending",
        assigned_at=timezone.now(),
        activated_at=timezone.now(),
    )
    notify(
        substitute_request.nominee_user_id,
        "task_assigned",
        "Substitute consent requested",
        "A leave request needs your responsibility coverage response.",
        task,
    )
    return task


@transaction.atomic
def activate_next(*, subject):
    kwargs = _subject_kwargs(subject)
    task = (
        WorkflowTask.objects.select_for_update()
        .filter(**kwargs, status="queued")
        .order_by("sequence", "id")
        .first()
    )
    if task is None:
        return None
    now = timezone.now()
    task.status = "pending"
    task.assigned_at = now
    task.activated_at = now
    task.due_at = _task_deadline(task.kind)
    task.save(update_fields=["status", "assigned_at", "activated_at", "due_at", "updated_at"])
    notify(
        task.assignee_user_id,
        "task_assigned",
        "ELM action assigned",
        f"You have an actionable {task.get_kind_display().lower()} task.",
        task,
    )
    return task


def cancel_subject_tasks(*, subject):
    kwargs = _subject_kwargs(subject)
    WorkflowTask.objects.filter(**kwargs, status__in=["pending", "queued"]).update(
        status="cancelled", updated_at=timezone.now()
    )


def record_event(*, subject, actor_user_id, event, from_status="", to_status="", details=None):
    return WorkflowEvent.objects.create(
        **_subject_kwargs(subject),
        actor_user_id=actor_user_id,
        event=event,
        from_status=from_status,
        to_status=to_status,
        details=details or {},
    )


def visible_task(principal, task_id, *, for_update=False):
    qs = WorkflowTask.objects.select_related("application", "action_request__application")
    if for_update:
        qs = qs.select_for_update()
    try:
        return qs.get(pk=task_id, assignee_user_id=principal.user_id)
    except WorkflowTask.DoesNotExist as exc:
        raise NotFoundError("Task not found.", code="not_found") from exc


def visible_application(principal, application_id, *, for_update=False):
    qs = LeaveApplication.objects.select_related("leave_type")
    if for_update:
        qs = qs.select_for_update()
    try:
        return qs.get(pk=application_id, employee_user_id=principal.user_id)
    except LeaveApplication.DoesNotExist as exc:
        raise NotFoundError("Leave application not found.", code="not_found") from exc


def visible_action(principal, action_id, *, for_update=False):
    qs = LeaveActionRequest.objects.select_related("application__leave_type")
    if for_update:
        qs = qs.select_for_update()
    try:
        return qs.get(pk=action_id, submitted_by_user_id=principal.user_id)
    except LeaveActionRequest.DoesNotExist as exc:
        raise NotFoundError("Leave action request not found.", code="not_found") from exc
