"""Event-triggered SLA reminders and notification-only escalations."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from modules.elm.models import ElmNotification, SlaEvent, SlaPolicy, WorkflowTask
from modules.elm.services.workflow import require


def process_sla_thresholds(*, now=None):
    now = now or timezone.now()
    processed = {"reminders": 0, "escalations": 0}
    policies = SlaPolicy.objects.filter(is_active=True)
    for policy in policies:
        tasks = WorkflowTask.objects.filter(
            kind=policy.task_kind,
            status="pending",
            activated_at__isnull=False,
        ).select_related("application", "action_request")
        for task in tasks.iterator():
            elapsed = now - task.activated_at
            if (
                policy.reminder_after_hours is not None
                and elapsed >= timedelta(hours=policy.reminder_after_hours)
                and not SlaEvent.objects.filter(task=task, kind="reminder").exists()
                and _record_threshold(task.pk, "reminder", task.assignee_user_id, now)
            ):
                processed["reminders"] += 1
            if (
                policy.escalation_after_hours is not None
                and elapsed >= timedelta(hours=policy.escalation_after_hours)
                and not SlaEvent.objects.filter(task=task, kind="escalation").exists()
            ):
                if policy.escalation_user_id is None:
                    continue
                if _record_threshold(task.pk, "escalation", policy.escalation_user_id, now):
                    processed["escalations"] += 1
    return processed


@transaction.atomic
def _record_threshold(task_id, kind, recipient_user_id, now):
    try:
        task = WorkflowTask.objects.select_for_update().get(pk=task_id)
    except WorkflowTask.DoesNotExist:
        return False
    if task.status != "pending" or task.activated_at is None:
        return False
    if SlaEvent.objects.filter(task=task, kind=kind).exists():
        return False
    SlaEvent.objects.create(
        task=task,
        kind=kind,
        recipient_user_id=recipient_user_id,
        acted_at=now,
        details={"task_kind": task.kind},
    )
    title = "ELM task reminder" if kind == "reminder" else "ELM task escalation"
    body = f"The {task.get_kind_display().lower()} task is still pending."
    ElmNotification.objects.create(
        recipient_user_id=recipient_user_id,
        kind=f"sla_{kind}",
        title=title,
        body=body,
        task=task,
    )
    return True


def run_sla(actor, *, now=None):
    require(actor, "leave_elm.sla.manage")
    return process_sla_thresholds(now=now)
