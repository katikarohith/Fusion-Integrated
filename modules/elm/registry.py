"""Server-owned ELM module registration, navigation and IAM grants."""

MODULE = {
    "code": "leave_elm",
    "label": "Leave Management",
    "icon": "FaCalendarAlt",
    "base_path": "/leave",
    "nav_section": "Leave",
    "sort_order": 30,
    "status": "active",
}

NAV_ITEMS = [
    {
        "code": "leave.apply",
        "label": "Apply for Leave",
        "icon": "FaCalendarAlt",
        "to": "/leave/apply",
        "required_permission": "leave_elm.application.apply",
        "sort_order": 10,
    },
    {
        "code": "leave.mine",
        "label": "My Leave",
        "icon": "FaClipboardList",
        "to": "/leave/mine",
        "required_permission": "leave_elm.application.view",
        "sort_order": 20,
    },
    {
        "code": "leave.balances",
        "label": "Balances and History",
        "icon": "FaChartBar",
        "to": "/leave/balances",
        "required_permission": "leave_elm.balance.view",
        "sort_order": 30,
    },
    {
        "code": "leave.tasks",
        "label": "Workflow Tasks",
        "icon": "FaUserCheck",
        "to": "/leave/tasks",
        "required_permission": "leave_elm.workflow.act",
        "sort_order": 40,
    },
    {
        "code": "leave.admin",
        "label": "Leave Configuration",
        "icon": "FaCog",
        "to": "/leave/admin",
        "required_permission": "leave_elm.policy.manage",
        "sort_order": 50,
    },
]

PERMISSIONS = [
    ("leave_elm.application.view", "View own leave applications"),
    ("leave_elm.application.apply", "Submit and withdraw leave requests"),
    ("leave_elm.application.export", "Export own leave application"),
    ("leave_elm.workflow.act", "Act on an assigned leave workflow task"),
    ("leave_elm.substitute.respond", "Respond to substitute requests"),
    ("leave_elm.balance.view", "View own balances and account history"),
    ("leave_elm.policy.manage", "Manage leave policy, routes, and employee context"),
    ("leave_elm.calendar.manage", "Maintain and publish leave calendars"),
    ("leave_elm.sla.manage", "Configure and process workflow SLA thresholds"),
    ("leave_elm.record.manage", "Maintain authorized leave records and balances"),
    ("leave_elm.offline.record", "Synchronize already sanctioned offline leave"),
    ("leave_elm.year_end.process", "Run year-end leave-account processing"),
]
SYSTEM_PERMISSIONS = []
SCOPE_PERMISSIONS = []

_EMPLOYEE = [
    "leave_elm.application.view",
    "leave_elm.application.apply",
    "leave_elm.application.export",
    "leave_elm.balance.view",
]
_WORKFLOW_ACTOR = ["leave_elm.application.view", "leave_elm.workflow.act"]
_ROLE_GRANTS = {
    "Employee": _EMPLOYEE,
    "Substitute / Responsibility Holder": [
        "leave_elm.application.view",
        "leave_elm.substitute.respond",
    ],
    "Unit Head": _WORKFLOW_ACTOR,
    "Establishment": _WORKFLOW_ACTOR,
    "Deputy Registrar (Estt.)": _WORKFLOW_ACTOR,
    "Dean": _WORKFLOW_ACTOR,
    "Registrar": _WORKFLOW_ACTOR,
    "Director": _WORKFLOW_ACTOR,
    "Leave Administrator": [
        "leave_elm.application.view",
        "leave_elm.balance.view",
        "leave_elm.policy.manage",
        "leave_elm.calendar.manage",
        "leave_elm.sla.manage",
        "leave_elm.record.manage",
        "leave_elm.offline.record",
        "leave_elm.year_end.process",
    ],
}
ROLE_GRANTS = _ROLE_GRANTS
