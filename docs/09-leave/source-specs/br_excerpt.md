# 1. Business Rule Index

| BR ID | Rule Name | Type | Status | Related CFRs |
|---|---|---|---|---|
| BR-EL-001 | Supported leave-category eligibility | Eligibility | Active | CFR-EL-002–003 |
| BR-EL-002 | Casual Leave entitlement and lapse | Entitlement | Active | CFR-EL-004, CFR-EL-028 |
| BR-EL-003 | Restricted Holiday entitlement and applicability | Entitlement / Calendar | Active | CFR-EL-005, CFR-EL-025, CFR-EL-028 |
| BR-EL-004 | Special Casual Leave entitlement and admissibility | Entitlement / Authority | Active | CFR-EL-006, CFR-EL-028 |
| BR-EL-005 | Non-faculty Earned Leave credit and carry-forward | Entitlement | Active | CFR-EL-007, CFR-EL-028 |
| BR-EL-006 | Faculty Vacation Leave entitlement and vacation-period applicability | Entitlement / Calendar | Active | CFR-EL-008 |
| BR-EL-007 | VL-to-EL year-end conversion | Calculation / Year-end | Active | CFR-EL-008, CFR-EL-028 |
| BR-EL-008 | Treatment of EL created by VL conversion | Account | Active | CFR-EL-008, CFR-EL-028 |
| BR-EL-009 | Commuted Leave entitlement and treatment | Entitlement / Evidence | Active | CFR-EL-009, CFR-EL-028 |
| BR-EL-010 | Half-day CL treatment | Calculation | Active | CFR-EL-004 |
| BR-EL-011 | Continuous-day counting | Counting | Active | CFR-EL-003, CFR-EL-010 |
| BR-EL-012 | Applicant non-overlap with half-day CL exception | Validation | Active | CFR-EL-003 |
| BR-EL-013 | Station Leave coupling | Scope / Information | Active | CFR-EL-002 |
| BR-EL-014 | Substitute eligibility | Eligibility | Active | CFR-EL-011–012 |
| BR-EL-015 | Substitute consent gate and decline recovery | Routing / Eligibility | Active | CFR-EL-012 |
| BR-EL-016 | Unit Head final scope for CL/RH | Authority | Active | CFR-EL-013, CFR-EL-019 |
| BR-EL-017 | Unit Head recommendation for higher-sanction leave | Authority / Routing | Active | CFR-EL-014, CFR-EL-019–020 |
| BR-EL-018 | Higher-sanction routing | Routing | Active | CFR-EL-014, CFR-EL-019–020 |
| BR-EL-019 | Authority resolution and optional Establishment step | Routing / Authority | Active | CFR-EL-014, CFR-EL-019–020 |
| BR-EL-020 | Director self-sanction | Authority / Exception | Active | CFR-EL-015 |
| BR-EL-021 | RETIRED — Modify Pending Request | Retired | RETIRED | — |
| BR-EL-022 | Immediate withdrawal of pending request | Lifecycle | Active | CFR-EL-018 |
| BR-EL-023 | Cancellation of approved leave before start | Lifecycle / Routing | Active | CFR-EL-019 |
| BR-EL-024 | Fresh application after cancellation | Lifecycle | Active | CFR-EL-019 |
| BR-EL-025 | Extension of ongoing EL/COL/VL | Lifecycle / Calculation | Active | CFR-EL-020 |
| BR-EL-026 | RETIRED IDENTIFIER | Retired | RETIRED | — |
| BR-EL-027 | Resumption applicability and review authority | Lifecycle / Authority | Active | CFR-EL-021 |
| BR-EL-028 | Normal, early, and late resumption outcome | Lifecycle / Account | Active | CFR-EL-021 |
| BR-EL-029 | Offline-sanctioned leave synchronization | Record integrity | Active | CFR-EL-027 |
| BR-EL-030 | Current configured policy and hierarchy | Configuration | Active | CFR-EL-003, CFR-EL-014, CFR-EL-024 |
| BR-EL-031 | Effective published holiday/RH calendar | Calendar | Active | CFR-EL-003, CFR-EL-005, CFR-EL-025 |
| BR-EL-032 | SLA reminder on still-pending task | Threshold / Notification | Active | CFR-EL-031 |
| BR-EL-033 | SLA escalation on still-pending task | Threshold / Escalation | Active | CFR-EL-032 |
| BR-EL-034 | No post-submission modification | Lifecycle constraint | Active | CFR-EL-017 |
| BR-EL-035 | Actionable task assignment notification | Notification | Active | CFR-EL-030 |
| BR-EL-036 | Role-based authorization | Authorization | Active | CFR-EL-001 |
| BR-EL-037 | Administrative maintenance is not sanctioning | Authorization / Record integrity | Active | CFR-EL-026–027 |
| BR-EL-038 | Configurable SLA thresholds | Configuration | Active | CFR-EL-029 |

## BR-EL-011 — Continuous-day counting

| Rule Type | Counting |
|---|---|
| Rule Statement | For EL, COL, and VL, intervening weekends and closed holidays inside the continuous approved interval count as leave days; this rule does not apply to CL, SCL, or RH. |
| Applies To | Leave-day calculation |
| Condition / Trigger | EL/COL/VL and excluded categories |
| Required Outcome / Constraint | Apply category-specific counting boundary exactly. |
| Related CFRs | CFR-EL-003, CFR-EL-010 |
| Related Use Cases | EL-UC-001, EL-UC-009 |
| Related Workflow(s) | CW-EL-01; CW-EL-03 |
| Status / Revision Note | Active. |

## BR-EL-012 — Applicant non-overlap with half-day CL exception

| Rule Type | Validation |
|---|---|
| Rule Statement | A new request shall not impermissibly overlap the employee's active pending or approved leave; first-half and second-half CL on the same date are non-overlapping when they occupy different halves. |
| Applies To | New-request validation |
| Condition / Trigger | Employee leave intervals |
| Required Outcome / Constraint | Block impermissible overlap; permit different CL halves on same date. |
| Related CFRs | CFR-EL-003 |
| Related Use Cases | EL-UC-001 |
| Related Workflow(s) | CW-EL-01 |
| Status / Revision Note | Confirmed PS gap. |

## BR-EL-022 — Immediate withdrawal of pending request

| Rule Type | Lifecycle |
|---|---|
| Rule Statement | A pending request may be withdrawn at any time before final approval; withdrawal is immediate, terminates remaining approval processing, blocks later approve/reject actions, and informs concerned roles. After final approval, withdrawal is unavailable. |
| Applies To | Pending request lifecycle |
| Condition / Trigger | Pending before final approval |
| Required Outcome / Constraint | Apply immediate terminal withdrawal effects. |
| Related CFRs | CFR-EL-018 |
| Related Use Cases | EL-UC-007 |
| Related Workflow(s) | CW-EL-01 |
| Status / Revision Note | Consolidated and strengthened. |

## BR-EL-023 — Cancellation of approved leave before start

| Rule Type | Lifecycle / Routing |
|---|---|
| Rule Statement | An approved leave may be cancelled only before its start date; cancellation uses the same applicable hierarchy, does not edit the approved leave in place, approval marks the leave Cancelled and restores/adjusts already deducted balance, while rejection leaves the original approval unchanged. |
| Applies To | Approved-leave cancellation |
| Condition / Trigger | Approved and not started |
| Required Outcome / Constraint | Enforce pre-start boundary and context-specific final effects. |
| Related CFRs | CFR-EL-019 |
| Related Use Cases | EL-UC-008, EL-UC-003–005 |
| Related Workflow(s) | CW-EL-02 |
| Status / Revision Note | Expanded with adjudicated outcome effects. |

## BR-EL-034 — No post-submission modification

| Rule Type | Lifecycle constraint |
|---|---|
| Rule Statement | A submitted pending leave request shall not be modified in place. If change is needed before final approval, the employee may withdraw and submit a new application if needed. |
| Applies To | Pending request |
| Condition / Trigger | Submitted and pending |
| Required Outcome / Constraint | Block in-place modification; preserve withdrawal/new-application route. |
| Related CFRs | CFR-EL-017 |
| Related Use Cases | EL-UC-007, EL-UC-001 |
| Related Workflow(s) | CW-EL-01 |
| Status / Revision Note | New replacement rule for retired BR-EL-021. |

## BR-EL-036 — Role-based authorization

| Rule Type | Authorization |
|---|---|
| Rule Statement | ELM capabilities shall be available only to users authorized for the corresponding employee, processing, sanctioning, or administrative role. |
| Applies To | All protected ELM actions |
| Condition / Trigger | Attempted protected action |
| Required Outcome / Constraint | Permit only role-authorized action. |
| Related CFRs | CFR-EL-001 |
| Related Use Cases | All actor UCs |
| Related Workflow(s) | All composite workflows |
| Status / Revision Note | New explicit cross-cutting rule from PS. |

