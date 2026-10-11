"""ELM-owned tables. IAM identities are plain integer references, never foreign keys."""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from core.db.mixins import TimeStampedModel


class LeaveType(TimeStampedModel):
    CODES = [
        ("CL", "Casual Leave"),
        ("RH", "Restricted Holiday"),
        ("SCL", "Special Casual Leave"),
        ("EL", "Earned Leave"),
        ("COL", "Commuted Leave"),
        ("VL", "Vacation Leave"),
    ]

    code = models.CharField(max_length=3, choices=CODES, unique=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "elm_leave_type"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class LeavePolicy(TimeStampedModel):
    EMPLOYEE_KINDS = [("faculty", "Faculty"), ("staff", "Non-faculty staff")]
    COUNTING_MODES = [
        ("continuous", "Continuous calendar days"),
        ("working", "Configured working days"),
        ("restricted_holiday", "Restricted holiday dates"),
    ]

    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="policies")
    employee_kind = models.CharField(max_length=12, choices=EMPLOYEE_KINDS)
    annual_entitlement = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    carry_forward = models.BooleanField(default=False)
    carry_forward_limit = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    counting_mode = models.CharField(max_length=20, choices=COUNTING_MODES)
    requires_medical_evidence = models.BooleanField(default=False)
    requires_vacation_period = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "elm_leave_policy"
        constraints = [
            models.UniqueConstraint(
                fields=["leave_type", "employee_kind"], name="elm_policy_type_kind_uniq"
            ),
            models.CheckConstraint(
                condition=Q(annual_entitlement__gte=0), name="elm_policy_entitlement_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(carry_forward_limit__isnull=True) | Q(carry_forward_limit__gte=0),
                name="elm_policy_carry_limit_nonneg",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.leave_type.code}/{self.employee_kind}"


class LeaveCalendar(TimeStampedModel):
    STATUSES = [("draft", "Draft"), ("published", "Published"), ("archived", "Archived")]

    year = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=12, choices=STATUSES, default="draft")
    # Weekday numbers use Python's Monday=0 ... Sunday=6 convention.
    weekly_closed_days = models.JSONField(default=list, blank=True)
    published_by_user_id = models.IntegerField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elm_leave_calendar"
        constraints = [
            models.UniqueConstraint(
                fields=["year"],
                condition=Q(status="published"),
                name="elm_calendar_year_published_uniq",
            ),
        ]
        ordering = ["-year", "-published_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.year}, {self.status})"


class CalendarDate(TimeStampedModel):
    KINDS = [("closed", "Closed holiday"), ("restricted_holiday", "Restricted holiday")]

    calendar = models.ForeignKey(LeaveCalendar, on_delete=models.CASCADE, related_name="dates")
    day = models.DateField()
    kind = models.CharField(max_length=20, choices=KINDS)
    label = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "elm_calendar_date"
        constraints = [
            models.UniqueConstraint(
                fields=["calendar", "day", "kind"], name="elm_calendar_day_kind_uniq"
            ),
        ]
        indexes = [models.Index(fields=["calendar", "day"], name="elm_calendar_day_idx")]


class VacationPeriod(TimeStampedModel):
    """Vacation-period snapshot supplied by the institute Academic Calendar."""

    calendar = models.ForeignKey(
        LeaveCalendar, on_delete=models.CASCADE, related_name="vacation_periods"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    label = models.CharField(max_length=120, blank=True)
    source_reference = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "elm_vacation_period"
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")), name="elm_vacation_period_valid"
            ),
        ]
        indexes = [
            models.Index(
                fields=["calendar", "start_date", "end_date"], name="elm_vacation_period_idx"
            )
        ]


class EmployeeProfile(TimeStampedModel):
    """ELM's configurable organizational context; identity remains IAM-owned."""

    user_id = models.IntegerField(unique=True)
    unit_code = models.CharField(max_length=80, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    is_director = models.BooleanField(default=False)
    updated_by_user_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "elm_employee_profile"


class RouteRule(TimeStampedModel):
    REQUEST_KINDS = [
        ("leave", "New leave"),
        ("cancellation", "Cancellation"),
        ("extension", "Extension"),
        ("resumption", "Resumption"),
    ]
    EMPLOYEE_KINDS = [("faculty", "Faculty"), ("staff", "Non-faculty staff")]

    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="route_rules")
    request_kind = models.CharField(max_length=16, choices=REQUEST_KINDS)
    employee_kind = models.CharField(max_length=12, choices=EMPLOYEE_KINDS)
    unit_code = models.CharField(max_length=80, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    director_applicant = models.BooleanField(default=False)
    requires_substitute = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    updated_by_user_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "elm_route_rule"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "leave_type",
                    "request_kind",
                    "employee_kind",
                    "unit_code",
                    "designation",
                    "director_applicant",
                ],
                name="elm_route_rule_context_uniq",
            ),
        ]


class RouteStep(TimeStampedModel):
    KINDS = [
        ("unit_head_final", "Unit Head final decision"),
        ("unit_head_recommendation", "Unit Head recommendation"),
        ("establishment", "Establishment processing"),
        ("sanctioning_authority", "Final sanctioning authority"),
        ("self_sanction", "Director self-sanction"),
        ("resumption_review", "Resumption review"),
    ]

    route = models.ForeignKey(RouteRule, on_delete=models.CASCADE, related_name="steps")
    sequence = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=32, choices=KINDS)
    assignee_user_id = models.IntegerField()
    assignee_role = models.CharField(max_length=100, blank=True)
    is_optional = models.BooleanField(default=False)

    class Meta:
        db_table = "elm_route_step"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["route", "sequence"], name="elm_route_step_sequence_uniq"
            ),
        ]


class LeaveBalance(TimeStampedModel):
    employee_user_id = models.IntegerField()
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="balances")
    year = models.PositiveSmallIntegerField()
    allotted = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    carried_forward = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    used = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    reserved = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    adjustments = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    expired = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))

    class Meta:
        db_table = "elm_leave_balance"
        constraints = [
            models.UniqueConstraint(
                fields=["employee_user_id", "leave_type", "year"],
                name="elm_balance_user_type_year_uniq",
            ),
            models.CheckConstraint(
                condition=Q(allotted__gte=0), name="elm_balance_allotted_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(carried_forward__gte=0), name="elm_balance_carry_nonneg"
            ),
            models.CheckConstraint(condition=Q(used__gte=0), name="elm_balance_used_nonneg"),
            models.CheckConstraint(
                condition=Q(reserved__gte=0), name="elm_balance_reserved_nonneg"
            ),
            models.CheckConstraint(condition=Q(expired__gte=0), name="elm_balance_expired_nonneg"),
        ]
        indexes = [
            models.Index(fields=["employee_user_id", "year"], name="elm_balance_user_year_idx"),
        ]

    @property
    def available(self) -> Decimal:
        return (
            self.allotted
            + self.carried_forward
            + self.adjustments
            - self.used
            - self.reserved
            - self.expired
        )


class LeaveApplication(TimeStampedModel):
    STATUSES = [
        ("awaiting_substitute", "Awaiting substitute"),
        ("applicant_action_required", "Applicant action required"),
        ("pending_approval", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
        ("cancellation_pending", "Cancellation pending"),
        ("cancelled", "Cancelled"),
    ]
    DAY_PARTS = [("full", "Full day"), ("first_half", "First half"), ("second_half", "Second half")]
    ORIGINS = [("online", "Online"), ("offline", "Authorized offline sanction")]

    employee_user_id = models.IntegerField()
    employee_kind = models.CharField(max_length=12, choices=RouteRule.EMPLOYEE_KINDS)
    unit_code = models.CharField(max_length=80, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    director_applicant = models.BooleanField(default=False)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="applications")
    start_date = models.DateField()
    end_date = models.DateField()
    day_part = models.CharField(max_length=12, choices=DAY_PARTS, default="full")
    days = models.DecimalField(max_digits=7, decimal_places=2)
    reason = models.TextField()
    station_leave_required = models.BooleanField(default=False)
    station_leave_details = models.CharField(max_length=500, blank=True)
    medical_evidence_reference = models.CharField(max_length=300, blank=True)
    substitute_required = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=STATUSES, default="pending_approval")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by_user_id = models.IntegerField(null=True, blank=True)
    origin = models.CharField(max_length=12, choices=ORIGINS, default="online")
    offline_reference = models.CharField(max_length=300, blank=True)
    offline_sanctioned_by_user_id = models.IntegerField(null=True, blank=True)
    offline_sanction_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "elm_leave_application"
        indexes = [
            models.Index(fields=["employee_user_id", "status"], name="elm_app_user_status_idx"),
            models.Index(fields=["status", "start_date"], name="elm_app_status_start_idx"),
            models.Index(
                fields=["leave_type", "start_date", "end_date"], name="elm_app_type_period_idx"
            ),
        ]


class LeaveActionRequest(TimeStampedModel):
    KINDS = [
        ("cancellation", "Cancellation"),
        ("extension", "Extension"),
        ("resumption", "Resumption"),
    ]
    STATUSES = [
        ("awaiting_substitute", "Awaiting substitute"),
        ("applicant_action_required", "Applicant action required"),
        ("pending_approval", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    application = models.ForeignKey(
        LeaveApplication, on_delete=models.PROTECT, related_name="actions"
    )
    kind = models.CharField(max_length=16, choices=KINDS)
    requested_end_date = models.DateField(null=True, blank=True)
    actual_resumption_date = models.DateField(null=True, blank=True)
    days = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    reason = models.TextField(blank=True)
    medical_evidence_reference = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=32, choices=STATUSES, default="pending_approval")
    submitted_by_user_id = models.IntegerField()
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elm_leave_action_request"
        indexes = [
            models.Index(
                fields=["application", "kind", "status"], name="elm_action_app_kind_status_idx"
            )
        ]


class SubstituteRequest(TimeStampedModel):
    STATUSES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("superseded", "Superseded"),
    ]

    application = models.ForeignKey(
        LeaveApplication,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="substitutes",
    )
    action_request = models.ForeignKey(
        LeaveActionRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="substitutes",
    )
    nominee_user_id = models.IntegerField()
    responsibility_start = models.DateField()
    responsibility_end = models.DateField()
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elm_substitute_request"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(application__isnull=False, action_request__isnull=True)
                    | Q(application__isnull=True, action_request__isnull=False)
                ),
                name="elm_substitute_one_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["nominee_user_id", "status"], name="elm_substitute_nominee_idx")
        ]


class WorkflowTask(TimeStampedModel):
    KINDS = [*RouteStep.KINDS, ("substitute", "Substitute consent")]
    STATUSES = [
        ("queued", "Queued"),
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    RESULTS = [
        ("approve", "Approved"),
        ("reject", "Rejected"),
        ("recommend", "Recommended"),
        ("not_recommend", "Not recommended"),
        ("forward", "Forwarded"),
        ("accept", "Accepted"),
        ("decline", "Declined"),
    ]

    application = models.ForeignKey(
        LeaveApplication, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks"
    )
    action_request = models.ForeignKey(
        LeaveActionRequest, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks"
    )
    kind = models.CharField(max_length=32, choices=KINDS)

    sequence = models.PositiveSmallIntegerField(default=1)
    assignee_user_id = models.IntegerField()
    assignee_role = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    result = models.CharField(max_length=16, choices=RESULTS, blank=True)
    note = models.TextField(blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elm_workflow_task"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(application__isnull=False, action_request__isnull=True)
                    | Q(application__isnull=True, action_request__isnull=False)
                ),
                name="elm_task_one_subject",
            ),
        ]
        indexes = [
            models.Index(
                fields=["assignee_user_id", "status", "assigned_at"],
                name="elm_task_assignee_status_idx",
            ),
        ]


class LeaveReservation(TimeStampedModel):
    STATUSES = [("reserved", "Reserved"), ("posted", "Posted"), ("released", "Released")]

    application = models.ForeignKey(
        LeaveApplication,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reservations",
    )
    action_request = models.ForeignKey(
        LeaveActionRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reservations",
    )
    balance = models.ForeignKey(LeaveBalance, on_delete=models.PROTECT, related_name="reservations")
    days = models.DecimalField(max_digits=7, decimal_places=2)
    status = models.CharField(max_length=12, choices=STATUSES, default="reserved")

    class Meta:
        db_table = "elm_leave_reservation"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(application__isnull=False, action_request__isnull=True)
                    | Q(application__isnull=True, action_request__isnull=False)
                ),
                name="elm_reservation_one_subject",
            ),
            models.CheckConstraint(condition=Q(days__gt=0), name="elm_reservation_days_positive"),
        ]


class LeaveLedgerEntry(TimeStampedModel):
    TYPES = [
        ("credit", "Annual credit"),
        ("carry", "Carry-forward"),
        ("reserve", "Reserved"),
        ("use", "Used"),
        ("release", "Reservation released"),
        ("adjustment", "Adjustment"),
        ("lapse", "Lapsed"),
        ("conversion", "Conversion"),
        ("resumption", "Resumption adjustment"),
        ("offline", "Offline synchronization"),
        ("cancellation", "Cancellation reversal"),
    ]

    balance = models.ForeignKey(
        LeaveBalance, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    amount = models.DecimalField(max_digits=7, decimal_places=2)
    kind = models.CharField(max_length=16, choices=TYPES)
    source_kind = models.CharField(max_length=24, blank=True)
    source_id = models.IntegerField(null=True, blank=True)
    actor_user_id = models.IntegerField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "elm_leave_ledger"
        indexes = [
            models.Index(fields=["balance", "created_at"], name="elm_ledger_balance_time_idx")
        ]


class WorkflowEvent(TimeStampedModel):
    application = models.ForeignKey(
        LeaveApplication, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    action_request = models.ForeignKey(
        LeaveActionRequest, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    actor_user_id = models.IntegerField(null=True, blank=True)
    event = models.CharField(max_length=40)
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "elm_workflow_event"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(application__isnull=False, action_request__isnull=True)
                    | Q(application__isnull=True, action_request__isnull=False)
                ),
                name="elm_event_one_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["application", "created_at"], name="elm_event_app_time_idx")
        ]


class YearEndRun(TimeStampedModel):
    STATUSES = [("running", "Running"), ("completed", "Completed"), ("failed", "Failed")]

    year = models.PositiveSmallIntegerField(unique=True)
    processed_by_user_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="running")
    summary = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elm_year_end_run"


class LeaveConfigurationEvent(TimeStampedModel):
    actor_user_id = models.IntegerField(null=True, blank=True)
    event = models.CharField(max_length=40)
    object_kind = models.CharField(max_length=32)
    object_id = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "elm_configuration_event"
        indexes = [
            models.Index(
                fields=["object_kind", "object_id", "created_at"],
                name="elm_config_event_object_idx",
            )
        ]


class YearEndItem(TimeStampedModel):
    STATUSES = [("completed", "Completed"), ("failed", "Failed")]

    run = models.ForeignKey(YearEndRun, on_delete=models.CASCADE, related_name="items")
    balance = models.ForeignKey(
        LeaveBalance, on_delete=models.PROTECT, related_name="year_end_items"
    )
    status = models.CharField(max_length=12, choices=STATUSES)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "elm_year_end_item"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "balance"], name="elm_year_end_item_run_balance_uniq"
            ),
        ]


class ElmNotification(TimeStampedModel):
    recipient_user_id = models.IntegerField()
    kind = models.CharField(max_length=32)
    title = models.CharField(max_length=180)
    body = models.CharField(max_length=500)
    task = models.ForeignKey(
        WorkflowTask, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elm_notification"
        indexes = [
            models.Index(
                fields=["recipient_user_id", "read_at", "created_at"],
                name="elm_notification_user_idx",
            )
        ]


class SlaPolicy(TimeStampedModel):
    task_kind = models.CharField(max_length=32, choices=WorkflowTask.KINDS)
    reminder_after_hours = models.PositiveIntegerField(null=True, blank=True)
    escalation_after_hours = models.PositiveIntegerField(null=True, blank=True)
    escalation_user_id = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "elm_sla_policy"
        constraints = [
            models.UniqueConstraint(
                fields=["task_kind"],
                condition=Q(is_active=True),
                name="elm_sla_policy_kind_active_uniq",
            ),
            models.CheckConstraint(
                condition=Q(reminder_after_hours__isnull=True)
                | Q(escalation_after_hours__isnull=True)
                | Q(escalation_after_hours__gte=models.F("reminder_after_hours")),
                name="elm_sla_threshold_order",
            ),
        ]


class SlaEvent(TimeStampedModel):
    KINDS = [("reminder", "Reminder"), ("escalation", "Escalation")]

    task = models.ForeignKey(WorkflowTask, on_delete=models.CASCADE, related_name="sla_events")
    kind = models.CharField(max_length=12, choices=KINDS)
    recipient_user_id = models.IntegerField()
    acted_at = models.DateTimeField()
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "elm_sla_event"
        constraints = [
            models.UniqueConstraint(fields=["task", "kind"], name="elm_sla_event_once_uniq"),
        ]
