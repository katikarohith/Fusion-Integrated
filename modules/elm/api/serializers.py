"""ELM API input validation and read representations."""

from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from modules.elm.models import (
    CalendarDate,
    ElmNotification,
    LeaveActionRequest,
    LeaveApplication,
    LeaveBalance,
    LeaveCalendar,
    LeaveLedgerEntry,
    LeavePolicy,
    LeaveType,
    RouteRule,
    RouteStep,
    SlaPolicy,
    VacationPeriod,
    WorkflowTask,
)


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "code", "name", "is_active"]


class LeavePolicySerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)

    class Meta:
        model = LeavePolicy
        fields = [
            "id",
            "leave_type_code",
            "employee_kind",
            "annual_entitlement",
            "carry_forward",
            "carry_forward_limit",
            "counting_mode",
            "requires_medical_evidence",
            "requires_vacation_period",
            "is_active",
        ]


class BalanceSerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    available = serializers.SerializerMethodField()

    class Meta:
        model = LeaveBalance
        fields = [
            "id",
            "leave_type_code",
            "leave_type_name",
            "year",
            "allotted",
            "carried_forward",
            "used",
            "reserved",
            "adjustments",
            "expired",
            "available",
        ]

    @extend_schema_field(serializers.DecimalField(max_digits=7, decimal_places=2))
    def get_available(self, obj):
        return obj.available


class LedgerSerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source="balance.leave_type.code", read_only=True)
    year = serializers.IntegerField(source="balance.year", read_only=True)

    class Meta:
        model = LeaveLedgerEntry
        fields = ["id", "leave_type_code", "year", "kind", "amount", "reason", "created_at"]


@extend_schema_serializer(component_name="ElmApplication")
class ApplicationSerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = LeaveApplication
        fields = [
            "id",
            "employee_user_id",
            "employee_kind",
            "leave_type_code",
            "leave_type_name",
            "start_date",
            "end_date",
            "day_part",
            "days",
            "reason",
            "station_leave_required",
            "station_leave_details",
            "medical_evidence_reference",
            "substitute_required",
            "status",
            "submitted_at",
            "approved_at",
            "approved_by_user_id",
            "origin",
            "offline_reference",
            "offline_sanctioned_by_user_id",
            "offline_sanction_date",
            "created_at",
        ]
        read_only_fields = fields


class ActionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveActionRequest
        fields = [
            "id",
            "application_id",
            "kind",
            "requested_end_date",
            "actual_resumption_date",
            "days",
            "reason",
            "medical_evidence_reference",
            "status",
            "submitted_by_user_id",
            "submitted_at",
            "created_at",
        ]
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer):
    employee_user_id = serializers.SerializerMethodField()
    leave_type_code = serializers.SerializerMethodField()
    action_kind = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowTask
        fields = [
            "id",
            "application_id",
            "action_request_id",
            "employee_user_id",
            "leave_type_code",
            "action_kind",
            "kind",
            "assignee_role",
            "status",
            "result",
            "note",
            "assigned_at",
            "activated_at",
            "due_at",
            "completed_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_employee_user_id(self, obj):
        if obj.application_id:
            return obj.application.employee_user_id
        return obj.action_request.application.employee_user_id

    @extend_schema_field(serializers.CharField())
    def get_leave_type_code(self, obj):
        if obj.application_id:
            return obj.application.leave_type.code
        return obj.action_request.application.leave_type.code

    @extend_schema_field(serializers.CharField())
    def get_action_kind(self, obj):
        return obj.action_request.kind if obj.action_request_id else "leave"


class NotificationSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ElmNotification
        fields = ["id", "kind", "title", "body", "task_id", "read_at", "created_at"]
        read_only_fields = fields


class RouteStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteStep
        fields = ["sequence", "kind", "assignee_user_id", "assignee_role", "is_optional"]


class RouteSerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    steps = RouteStepSerializer(many=True, read_only=True)

    class Meta:
        model = RouteRule
        fields = [
            "id",
            "leave_type_code",
            "request_kind",
            "employee_kind",
            "unit_code",
            "designation",
            "director_applicant",
            "requires_substitute",
            "is_active",
            "steps",
        ]


class CalendarDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarDate
        fields = ["day", "kind", "label"]


class VacationPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = VacationPeriod
        fields = ["start_date", "end_date", "label", "source_reference"]


class CalendarSerializer(serializers.ModelSerializer):
    dates = CalendarDateSerializer(many=True, read_only=True)
    vacation_periods = VacationPeriodSerializer(many=True, read_only=True)

    class Meta:
        model = LeaveCalendar
        fields = [
            "id",
            "year",
            "name",
            "status",
            "weekly_closed_days",
            "published_by_user_id",
            "published_at",
            "dates",
            "vacation_periods",
        ]


class SlaPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SlaPolicy
        fields = [
            "id",
            "task_kind",
            "reminder_after_hours",
            "escalation_after_hours",
            "escalation_user_id",
            "is_active",
        ]


class ApplyInputSerializer(serializers.Serializer):
    leave_type_id = serializers.IntegerField(min_value=1)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    day_part = serializers.ChoiceField(choices=LeaveApplication.DAY_PARTS, default="full")
    reason = serializers.CharField(max_length=2000, trim_whitespace=True)
    station_leave_required = serializers.BooleanField(default=False)
    station_leave_details = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    medical_evidence_reference = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    substitute_user_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )


class SubstituteInputSerializer(serializers.Serializer):
    nominee_user_id = serializers.IntegerField(min_value=1)


class SubstituteDecisionInputSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class TaskDecisionInputSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["approve", "reject", "recommend", "not_recommend", "forward"]
    )
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class ActionInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=LeaveActionRequest.KINDS)
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    requested_end_date = serializers.DateField(required=False, allow_null=True)
    actual_resumption_date = serializers.DateField(required=False, allow_null=True)
    substitute_user_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    medical_evidence_reference = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )


class PolicyInputSerializer(serializers.Serializer):
    leave_type_code = serializers.ChoiceField(choices=[code for code, _ in LeaveType.CODES])
    employee_kind = serializers.ChoiceField(choices=LeavePolicy.EMPLOYEE_KINDS)
    annual_entitlement = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0)
    carry_forward = serializers.BooleanField()
    carry_forward_limit = serializers.DecimalField(
        max_digits=7, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    counting_mode = serializers.ChoiceField(choices=LeavePolicy.COUNTING_MODES)
    requires_medical_evidence = serializers.BooleanField(default=False)
    requires_vacation_period = serializers.BooleanField(default=False)


class EmployeeProfileInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    unit_code = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    designation = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    is_director = serializers.BooleanField(default=False)


class RouteStepInputSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=1, required=False)
    kind = serializers.ChoiceField(choices=RouteStep.KINDS)
    assignee_user_id = serializers.IntegerField(min_value=1)
    assignee_role = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    is_optional = serializers.BooleanField(default=False)


class RouteInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, required=False)
    leave_type_code = serializers.ChoiceField(choices=[code for code, _ in LeaveType.CODES])
    request_kind = serializers.ChoiceField(choices=RouteRule.REQUEST_KINDS)
    employee_kind = serializers.ChoiceField(choices=RouteRule.EMPLOYEE_KINDS)
    unit_code = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    designation = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    director_applicant = serializers.BooleanField(default=False)
    requires_substitute = serializers.BooleanField(default=False)
    steps = RouteStepInputSerializer(many=True, allow_empty=False)


class CalendarDateInputSerializer(serializers.Serializer):
    day = serializers.DateField()
    kind = serializers.ChoiceField(choices=CalendarDate.KINDS)
    label = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class VacationPeriodInputSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    label = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    source_reference = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )


class CalendarInputSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=9999)
    name = serializers.CharField(max_length=120)
    weekly_closed_days = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), allow_empty=True
    )
    dates = CalendarDateInputSerializer(many=True, allow_empty=True)
    vacation_periods = VacationPeriodInputSerializer(many=True, allow_empty=True)

    def validate(self, attrs):
        year = attrs["year"]
        for item in attrs["dates"]:
            if item["day"].year != year:
                raise serializers.ValidationError(
                    {"dates": "Every date must belong to the selected year."}
                )
        date_keys = [(item["day"], item["kind"]) for item in attrs["dates"]]
        if len(date_keys) != len(set(date_keys)):
            raise serializers.ValidationError({"dates": "Duplicate calendar date and kind."})
        for item in attrs["vacation_periods"]:
            if item["start_date"].year > year or item["end_date"].year < year:
                raise serializers.ValidationError(
                    {"vacation_periods": "Each vacation period must include the selected year."}
                )
            if item["end_date"] < item["start_date"]:
                raise serializers.ValidationError(
                    {"vacation_periods": "Vacation period end precedes its start."}
                )
        return attrs


class SlaInputSerializer(serializers.Serializer):
    task_kind = serializers.ChoiceField(choices=WorkflowTask.KINDS)
    reminder_after_hours = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    escalation_after_hours = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    escalation_user_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class OfflineLeaveInputSerializer(serializers.Serializer):
    employee_user_id = serializers.IntegerField(min_value=1)
    leave_type_code = serializers.ChoiceField(choices=[code for code, _ in LeaveType.CODES])
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    day_part = serializers.ChoiceField(choices=LeaveApplication.DAY_PARTS, default="full")
    reason = serializers.CharField(max_length=2000)
    station_leave_required = serializers.BooleanField(default=False)
    station_leave_details = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    medical_evidence_reference = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    sanction_reference = serializers.CharField(max_length=300)
    sanctioned_by_user_id = serializers.IntegerField(min_value=1)
    sanction_date = serializers.DateField()


class BalanceAdjustmentInputSerializer(serializers.Serializer):
    balance_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=7, decimal_places=2)
    reason = serializers.CharField(max_length=500)


class YearEndInputSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=9999)


class ApplicationActionInputSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class NotificationReadInputSerializer(serializers.Serializer):
    read = serializers.BooleanField(default=True)


class EmployeeProfileSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    unit_code = serializers.CharField(allow_blank=True)
    designation = serializers.CharField(allow_blank=True)
    is_director = serializers.BooleanField()


class SlaProcessResultSerializer(serializers.Serializer):
    reminders = serializers.IntegerField()
    escalations = serializers.IntegerField()


class YearEndResultSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    status = serializers.CharField()
    summary = serializers.JSONField()
    completed_at = serializers.DateTimeField(allow_null=True)
