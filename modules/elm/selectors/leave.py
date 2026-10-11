"""All ELM reads are scoped here; views do not build ORM querysets."""

from django.db.models import Q

from modules.elm.models import (
    ElmNotification,
    LeaveActionRequest,
    LeaveApplication,
    LeaveBalance,
    LeaveLedgerEntry,
    LeaveType,
    WorkflowTask,
)


def my_applications(principal):
    return (
        LeaveApplication.objects.filter(employee_user_id=principal.user_id)
        .select_related("leave_type")
        .order_by("-submitted_at", "-id")
    )


def my_actions(principal):
    return (
        LeaveActionRequest.objects.filter(submitted_by_user_id=principal.user_id)
        .select_related("application__leave_type")
        .order_by("-submitted_at", "-id")
    )


def visible_applications(principal):
    return (
        LeaveApplication.objects.filter(
            Q(employee_user_id=principal.user_id) | Q(tasks__assignee_user_id=principal.user_id)
        )
        .distinct()
        .select_related("leave_type")
        .order_by("-submitted_at", "-id")
    )


def assigned_tasks(principal, *, pending_only=False):
    qs = WorkflowTask.objects.filter(assignee_user_id=principal.user_id).select_related(
        "application__leave_type", "action_request__application__leave_type"
    )
    if pending_only:
        qs = qs.filter(status="pending")
    return qs.order_by("-assigned_at", "-id")


def balances(principal):
    return (
        LeaveBalance.objects.filter(employee_user_id=principal.user_id)
        .select_related("leave_type")
        .order_by("-year", "leave_type__code")
    )


def ledger_entries(principal):
    return (
        LeaveLedgerEntry.objects.filter(balance__employee_user_id=principal.user_id)
        .select_related("balance__leave_type")
        .order_by("-created_at", "-id")
    )


def active_leave_types(employee_kind=None):
    qs = LeaveType.objects.filter(is_active=True)
    if employee_kind in {"faculty", "staff"}:
        qs = qs.filter(policies__employee_kind=employee_kind, policies__is_active=True).distinct()
    return qs.order_by("code")


def notifications(principal):
    return (
        ElmNotification.objects.filter(recipient_user_id=principal.user_id)
        .select_related("task")
        .order_by("-created_at", "-id")
    )
