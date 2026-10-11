from django.urls import path

from modules.elm.api import views

urlpatterns = [
    path("types", views.LeaveTypeListView.as_view(), name="elm-types"),
    path("applications", views.MyApplicationsView.as_view(), name="elm-applications"),
    path(
        "applications/<int:pk>/withdraw",
        views.ApplicationWithdrawView.as_view(),
        name="elm-application-withdraw",
    ),
    path(
        "applications/<int:pk>/substitute",
        views.SubstituteReplacementView.as_view(),
        name="elm-application-substitute",
    ),
    path(
        "applications/<int:pk>/actions",
        views.ActionRequestView.as_view(),
        name="elm-application-actions",
    ),
    path(
        "applications/<int:pk>/export",
        views.ApplicationExportView.as_view(),
        name="elm-application-export",
    ),
    path("actions", views.MyActionsView.as_view(), name="elm-actions"),
    path(
        "actions/<int:pk>/substitute",
        views.ActionSubstituteReplacementView.as_view(),
        name="elm-action-substitute",
    ),
    path(
        "actions/<int:pk>/withdraw", views.ActionWithdrawView.as_view(), name="elm-action-withdraw"
    ),
    path("balances", views.MyBalancesView.as_view(), name="elm-balances"),
    path("history", views.MyHistoryView.as_view(), name="elm-history"),
    path("tasks", views.TaskListView.as_view(), name="elm-tasks"),
    path("tasks/<int:pk>/decision", views.TaskDecisionView.as_view(), name="elm-task-decision"),
    path(
        "tasks/<int:pk>/substitute-response",
        views.SubstituteResponseView.as_view(),
        name="elm-substitute-response",
    ),
    path("notifications", views.NotificationsView.as_view(), name="elm-notifications"),
    path(
        "notifications/<int:pk>/read",
        views.NotificationReadView.as_view(),
        name="elm-notification-read",
    ),
    path("calendar", views.PublishedCalendarView.as_view(), name="elm-calendar"),
    path("admin/policies", views.AdminPoliciesView.as_view(), name="elm-admin-policies"),
    path(
        "admin/employee-profiles",
        views.AdminEmployeeProfileView.as_view(),
        name="elm-admin-employee-profiles",
    ),
    path("admin/routes", views.AdminRoutesView.as_view(), name="elm-admin-routes"),
    path("admin/calendars", views.AdminCalendarsView.as_view(), name="elm-admin-calendars"),
    path(
        "admin/calendars/<int:pk>/publish",
        views.CalendarPublishView.as_view(),
        name="elm-admin-calendar-publish",
    ),
    path("admin/sla", views.AdminSlaView.as_view(), name="elm-admin-sla"),
    path("admin/sla/process", views.AdminSlaProcessView.as_view(), name="elm-admin-sla-process"),
    path(
        "admin/offline-leaves",
        views.AdminOfflineLeaveView.as_view(),
        name="elm-admin-offline-leaves",
    ),
    path(
        "admin/balance-adjustments",
        views.AdminBalanceAdjustmentView.as_view(),
        name="elm-admin-balance-adjustments",
    ),
    path("admin/year-end", views.AdminYearEndView.as_view(), name="elm-admin-year-end"),
]
