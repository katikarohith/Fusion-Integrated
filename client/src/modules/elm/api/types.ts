export interface Page<T> { results: T[]; next: string | null; previous: string | null }
export interface LeaveType { id: number; code: string; name: string; is_active: boolean }
export interface Application {
  id: number; employee_user_id: number; employee_kind: "faculty" | "staff";
  leave_type_code: string; leave_type_name: string; start_date: string; end_date: string;
  day_part: string; days: string; reason: string; station_leave_required: boolean;
  station_leave_details: string; medical_evidence_reference: string;
  substitute_required: boolean; status: string; submitted_at: string | null;
  approved_at: string | null; origin: string; offline_reference: string; created_at: string;
}
export interface ActionRequest {
  id: number; application_id: number; kind: "cancellation" | "extension" | "resumption";
  requested_end_date: string | null; actual_resumption_date: string | null;
  days: string; reason: string; medical_evidence_reference: string;
  status: string; submitted_by_user_id: number; submitted_at: string | null;
  created_at: string;
}export interface Balance {
  id: number; leave_type_code: string; leave_type_name: string; year: number;
  allotted: string; carried_forward: string; used: string; reserved: string;
  adjustments: string; expired: string; available: string;
}
export interface LedgerEntry {
  id: number; leave_type_code: string; year: number; kind: string;
  amount: string; reason: string; created_at: string;
}
export interface Task {
  id: number; application_id: number | null; action_request_id: number | null;
  employee_user_id: number; leave_type_code: string; action_kind: string;
  kind: string; assignee_role: string; status: string; result: string; note: string;
  assigned_at: string | null; activated_at: string | null; due_at: string | null;
  completed_at: string | null;
}
export interface Notification {
  id: number; kind: string; title: string; body: string; task_id: number | null;
  read_at: string | null; created_at: string;
}
