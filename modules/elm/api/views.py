"""Thin ELM HTTP adapters. Ownership filters stay in selectors."""

import csv
from io import StringIO

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiTypes, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import CursorPagination
from fusion_auth.permissions import HasModuleGrant, HasPermission
from modules.elm.api.serializers import (
    ActionInputSerializer,
    ActionRequestSerializer,
    ApplicationSerializer,
    ApplyInputSerializer,
    BalanceAdjustmentInputSerializer,
    BalanceSerializer,
    CalendarInputSerializer,
    CalendarSerializer,
    EmployeeProfileInputSerializer,
    EmployeeProfileSerializer,
    LeavePolicySerializer,
    LeaveTypeSerializer,
    LedgerSerializer,
    NotificationReadInputSerializer,
    NotificationSerializer,
    OfflineLeaveInputSerializer,
    PolicyInputSerializer,
    RouteInputSerializer,
    RouteSerializer,
    SlaInputSerializer,
    SlaPolicySerializer,
    SlaProcessResultSerializer,
    SubstituteDecisionInputSerializer,
    SubstituteInputSerializer,
    TaskDecisionInputSerializer,
    TaskSerializer,
    YearEndInputSerializer,
    YearEndResultSerializer,
)
from modules.elm.models import LeaveCalendar, WorkflowEvent
from modules.elm.selectors import leave as selectors
from modules.elm.services import leave as leave_service
from modules.elm.services import policy as policy_service
from modules.elm.services import sla as sla_service
from modules.elm.services import year_end as year_end_service
from modules.elm.services.workflow import visible_application


def _page_schema(name, item_serializer):
    return inline_serializer(
        name=name,
        fields={
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": item_serializer(many=True),
        },
    )


def _list_response(request, queryset, serializer_class):
    paginator = CursorPagination()
    page = paginator.paginate_queryset(queryset, request, view=None)
    data = serializer_class(page, many=True).data
    return paginator.get_paginated_response(data)


class ElmAPIView(APIView):
    permission_codes = ()

    def get_permission_codes(self):
        return self.permission_codes

    def get_permissions(self):
        return [
            HasModuleGrant("leave_elm")(),
            HasPermission(*self.get_permission_codes())(),
        ]


class LeaveTypeListView(ElmAPIView):
    permission_codes = ("leave_elm.application.view", "leave_elm.application.apply")

    @extend_schema(responses=LeaveTypeSerializer(many=True))
    def get(self, request):
        types = selectors.active_leave_types(employee_kind=request.user.kind)
        return Response(LeaveTypeSerializer(types, many=True).data)


class MyApplicationsView(ElmAPIView):
    def get_permission_codes(self):
        return (
            ("leave_elm.application.apply",)
            if self.request.method == "POST"
            else ("leave_elm.application.view",)
        )

    @extend_schema(responses=_page_schema("ElmApplicationPage", ApplicationSerializer))
    def get(self, request):
        return _list_response(
            request, selectors.my_applications(request.user), ApplicationSerializer
        )

    @extend_schema(request=ApplyInputSerializer, responses=ApplicationSerializer)
    def post(self, request):
        serializer = ApplyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = leave_service.apply_for_leave(request.user, **serializer.validated_data)
        return Response(ApplicationSerializer(application).data, status=201)


class ApplicationWithdrawView(ElmAPIView):
    permission_codes = ("leave_elm.application.apply",)

    @extend_schema(request=None, responses=ApplicationSerializer)
    def post(self, request, pk):
        application = leave_service.withdraw_application(request.user, application_id=pk)
        return Response(ApplicationSerializer(application).data)


class SubstituteReplacementView(ElmAPIView):
    permission_codes = ("leave_elm.application.apply",)

    @extend_schema(request=SubstituteInputSerializer, responses=ApplicationSerializer)
    def post(self, request, pk):
        serializer = SubstituteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = leave_service.replace_substitute(
            request.user, application_id=pk, **serializer.validated_data
        )
        return Response(ApplicationSerializer(application).data)


class ActionRequestView(ElmAPIView):
    permission_codes = ("leave_elm.application.apply",)

    @extend_schema(request=ActionInputSerializer, responses=ActionRequestSerializer)
    def post(self, request, pk):
        serializer = ActionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = leave_service.request_leave_action(
            request.user, application_id=pk, **serializer.validated_data
        )
        return Response(ActionRequestSerializer(action).data, status=201)


class MyActionsView(ElmAPIView):
    permission_codes = ("leave_elm.application.view",)

    @extend_schema(responses=_page_schema("ElmActionRequestPage", ActionRequestSerializer))
    def get(self, request):
        return _list_response(request, selectors.my_actions(request.user), ActionRequestSerializer)


class ActionSubstituteReplacementView(ElmAPIView):
    permission_codes = ("leave_elm.application.apply",)

    @extend_schema(request=SubstituteInputSerializer, responses=ActionRequestSerializer)
    def post(self, request, pk):
        serializer = SubstituteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = leave_service.replace_action_substitute(
            request.user, action_id=pk, **serializer.validated_data
        )
        return Response(ActionRequestSerializer(action).data)


class ActionWithdrawView(ElmAPIView):
    permission_codes = ("leave_elm.application.apply",)

    @extend_schema(request=None, responses=ActionRequestSerializer)
    def post(self, request, pk):
        action = leave_service.withdraw_action(request.user, action_id=pk)
        return Response(ActionRequestSerializer(action).data)


class MyBalancesView(ElmAPIView):
    permission_codes = ("leave_elm.balance.view",)

    @extend_schema(responses=_page_schema("ElmBalancePage", BalanceSerializer))
    def get(self, request):
        return _list_response(request, leave_service.my_balances(request.user), BalanceSerializer)


class MyHistoryView(ElmAPIView):
    permission_codes = ("leave_elm.balance.view",)

    @extend_schema(responses=_page_schema("ElmLedgerPage", LedgerSerializer))
    def get(self, request):
        return _list_response(request, leave_service.my_history(request.user), LedgerSerializer)


class TaskListView(ElmAPIView):
    permission_codes = ("leave_elm.workflow.act", "leave_elm.substitute.respond")

    @extend_schema(responses=_page_schema("ElmTaskPage", TaskSerializer))
    def get(self, request):
        return _list_response(
            request, selectors.assigned_tasks(request.user, pending_only=True), TaskSerializer
        )


class TaskDecisionView(ElmAPIView):
    permission_codes = ("leave_elm.workflow.act",)

    @extend_schema(request=TaskDecisionInputSerializer, responses=TaskSerializer)
    def post(self, request, pk):
        serializer = TaskDecisionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = leave_service.decide_task(request.user, task_id=pk, **serializer.validated_data)
        return Response(TaskSerializer(task).data)


class SubstituteResponseView(ElmAPIView):
    permission_codes = ("leave_elm.substitute.respond",)

    @extend_schema(request=SubstituteDecisionInputSerializer, responses=TaskSerializer)
    def post(self, request, pk):
        serializer = SubstituteDecisionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = leave_service.respond_to_substitute(
            request.user, task_id=pk, **serializer.validated_data
        )
        return Response(TaskSerializer(task).data)


class NotificationsView(ElmAPIView):
    permission_codes = (
        "leave_elm.application.view",
        "leave_elm.workflow.act",
        "leave_elm.substitute.respond",
    )

    @extend_schema(responses=_page_schema("ElmNotificationPage", NotificationSerializer))
    def get(self, request):
        return _list_response(
            request, selectors.notifications(request.user), NotificationSerializer
        )


class NotificationReadView(ElmAPIView):
    permission_codes = ("leave_elm.application.view",)

    @extend_schema(request=NotificationReadInputSerializer, responses=NotificationSerializer)
    def post(self, request, pk):
        serializer = NotificationReadInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = leave_service.mark_notification_read(request.user, pk)
        return Response(NotificationSerializer(item).data)


class ApplicationExportView(ElmAPIView):
    permission_codes = ("leave_elm.application.export",)

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request, pk):
        application = visible_application(request.user, pk)
        events = WorkflowEvent.objects.filter(application=application).order_by("created_at")
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Value"])
        for key, value in [
            ("Application", application.pk),
            ("Employee", application.employee_user_id),
            ("Leave category", application.leave_type.code),
            ("Start date", application.start_date.isoformat()),
            ("End date", application.end_date.isoformat()),
            ("Days", application.days),
            ("Status", application.status),
            ("Reason", application.reason),
            ("Station Leave", application.station_leave_details),
        ]:
            cell = str(value)
            if cell.startswith(("=", "+", "-", "@")):
                cell = "'" + cell
            writer.writerow([key, cell])
        writer.writerow([])
        writer.writerow(["Event", "From", "To", "At"])
        for event in events:
            writer.writerow(
                [event.event, event.from_status, event.to_status, event.created_at.isoformat()]
            )
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="leave-application-{application.pk}.csv"'
        )
        return response


class AdminPoliciesView(ElmAPIView):
    permission_codes = ("leave_elm.policy.manage",)

    @extend_schema(responses=LeavePolicySerializer(many=True))
    def get(self, request):
        policies = policy_service.list_policies(request.user)
        return Response(LeavePolicySerializer(policies, many=True).data)

    @extend_schema(request=PolicyInputSerializer, responses=LeavePolicySerializer)
    def post(self, request):
        serializer = PolicyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = policy_service.update_policy(request.user, **serializer.validated_data)
        return Response(LeavePolicySerializer(policy).data, status=201)


class AdminEmployeeProfileView(ElmAPIView):
    permission_codes = ("leave_elm.policy.manage",)

    @extend_schema(request=EmployeeProfileInputSerializer, responses=EmployeeProfileSerializer)
    def post(self, request):
        serializer = EmployeeProfileInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = policy_service.update_employee_profile(request.user, **serializer.validated_data)
        return Response(
            EmployeeProfileSerializer(
                {
                    "user_id": profile.user_id,
                    "unit_code": profile.unit_code,
                    "designation": profile.designation,
                    "is_director": profile.is_director,
                }
            ).data,
            status=201,
        )


class AdminRoutesView(ElmAPIView):
    permission_codes = ("leave_elm.policy.manage",)

    @extend_schema(responses=RouteSerializer(many=True))
    def get(self, request):
        routes = policy_service.list_routes(request.user)
        return Response(RouteSerializer(routes, many=True).data)

    @extend_schema(request=RouteInputSerializer, responses=RouteSerializer)
    def post(self, request):
        serializer = RouteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        route_id = values.pop("id", None)
        route = policy_service.save_route(request.user, route_id=route_id, **values)
        return Response(RouteSerializer(route).data, status=201)


class AdminCalendarsView(ElmAPIView):
    permission_codes = ("leave_elm.calendar.manage",)

    @extend_schema(responses=CalendarSerializer(many=True))
    def get(self, request):
        return Response(
            CalendarSerializer(policy_service.list_calendars(request.user), many=True).data
        )

    @extend_schema(request=CalendarInputSerializer, responses=CalendarSerializer)
    def post(self, request):
        serializer = CalendarInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        calendar = policy_service.create_calendar(request.user, **serializer.validated_data)
        return Response(CalendarSerializer(calendar).data, status=201)


class CalendarPublishView(ElmAPIView):
    permission_codes = ("leave_elm.calendar.manage",)

    @extend_schema(request=None, responses=CalendarSerializer)
    def post(self, request, pk):
        calendar = policy_service.publish_calendar(request.user, calendar_id=pk)
        return Response(CalendarSerializer(calendar).data)


class AdminSlaView(ElmAPIView):
    permission_codes = ("leave_elm.sla.manage",)

    @extend_schema(responses=SlaPolicySerializer(many=True))
    def get(self, request):
        return Response(
            SlaPolicySerializer(policy_service.list_sla_policies(request.user), many=True).data
        )

    @extend_schema(request=SlaInputSerializer, responses=SlaPolicySerializer)
    def post(self, request):
        serializer = SlaInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = policy_service.save_sla_policy(request.user, **serializer.validated_data)
        return Response(SlaPolicySerializer(policy).data, status=201)


class AdminSlaProcessView(ElmAPIView):
    permission_codes = ("leave_elm.sla.manage",)

    @extend_schema(request=None, responses=SlaProcessResultSerializer)
    def post(self, request):
        return Response(sla_service.run_sla(request.user))


class AdminOfflineLeaveView(ElmAPIView):
    permission_codes = ("leave_elm.offline.record", "leave_elm.record.manage")

    @extend_schema(request=OfflineLeaveInputSerializer, responses=ApplicationSerializer)
    def post(self, request):
        serializer = OfflineLeaveInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = policy_service.record_offline_leave(request.user, **serializer.validated_data)
        return Response(ApplicationSerializer(application).data, status=201)


class AdminBalanceAdjustmentView(ElmAPIView):
    permission_codes = ("leave_elm.record.manage",)

    @extend_schema(request=BalanceAdjustmentInputSerializer, responses=BalanceSerializer)
    def post(self, request):
        serializer = BalanceAdjustmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        balance = policy_service.adjust_balance(request.user, **serializer.validated_data)
        return Response(BalanceSerializer(balance).data)


class AdminYearEndView(ElmAPIView):
    permission_codes = ("leave_elm.year_end.process",)

    @extend_schema(request=YearEndInputSerializer, responses=YearEndResultSerializer)
    def post(self, request):
        serializer = YearEndInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = year_end_service.run_year_end(request.user, **serializer.validated_data)
        return Response(
            {
                "year": run.year,
                "status": run.status,
                "summary": run.summary,
                "completed_at": run.completed_at,
            },
            status=200 if run.status == "completed" else 207,
        )


class PublishedCalendarView(ElmAPIView):
    permission_codes = ("leave_elm.application.view", "leave_elm.application.apply")

    @extend_schema(responses=CalendarSerializer(many=True))
    def get(self, request):
        from django.utils import timezone

        year_field = serializers.IntegerField(min_value=2000, max_value=9999)
        year = year_field.run_validation(
            request.query_params.get("year", timezone.localdate().year)
        )
        calendars = LeaveCalendar.objects.filter(status="published", year=year).prefetch_related(
            "dates", "vacation_periods"
        )
        return Response(CalendarSerializer(calendars, many=True).data)
