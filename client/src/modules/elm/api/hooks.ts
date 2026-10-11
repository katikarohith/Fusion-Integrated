import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "../../../lib/http";
import type {
  ActionRequest, Application, Balance, LedgerEntry, LeaveType, Notification, Page, Task,
} from "./types";

const ROOT = "/elm";
const KEY = "elm";
const invalidate = (client: ReturnType<typeof useQueryClient>) =>
  client.invalidateQueries({ queryKey: [KEY] });

export function useLeaveTypes() {
  return useQuery({
    queryKey: [KEY, "types"],
    queryFn: async () => (await http.get<LeaveType[]>(ROOT + "/types")).data,
  });
}

export function useApplications() {
  return useQuery({
    queryKey: [KEY, "applications"],
    queryFn: async () =>
      (await http.get<Page<Application>>(ROOT + "/applications")).data,
  });
}

export function useActions() {
  return useQuery({
    queryKey: [KEY, "actions"],
    queryFn: async () =>
      (await http.get<Page<ActionRequest>>(ROOT + "/actions")).data,
  });
}

export function useBalances() {
  return useQuery({
    queryKey: [KEY, "balances"],
    queryFn: async () => (await http.get<Page<Balance>>(ROOT + "/balances")).data,
  });
}

export function useHistory() {
  return useQuery({
    queryKey: [KEY, "history"],
    queryFn: async () =>
      (await http.get<Page<LedgerEntry>>(ROOT + "/history")).data,
  });
}

export function useTasks() {
  return useQuery({
    queryKey: [KEY, "tasks"],
    queryFn: async () => (await http.get<Page<Task>>(ROOT + "/tasks")).data,
    refetchInterval: 30_000,
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: [KEY, "notifications"],
    queryFn: async () =>
      (await http.get<Page<Notification>>(ROOT + "/notifications")).data,
  });
}

export function useCalendar(year: number) {
  return useQuery({
    queryKey: [KEY, "calendar", year],
    queryFn: async () =>
      (await http.get(ROOT + "/calendar", { params: { year } })).data,
  });
}

function usePost<T>(endpoint: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: Record<string, unknown>) =>
      (await http.post<T>(ROOT + endpoint, body)).data,
    onSuccess: () => invalidate(client),
  });
}

function usePostAt<T, V>(
  endpoint: (value: V) => string,
  body: (value: V) => Record<string, unknown>,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (value: V) =>
      (await http.post<T>(ROOT + endpoint(value), body(value))).data,
    onSuccess: () => invalidate(client),
  });
}

export function useApplyLeave() {
  return usePost<Application>("/applications");
}

export function useWithdrawLeave() {
  return usePostAt<Application, number>(
    (id) => "/applications/" + id + "/withdraw",
    () => ({}),
  );
}

export function useReplaceSubstitute() {
  return usePostAt<Application, { id: number; nominee_user_id: number }>(
    (value) => "/applications/" + value.id + "/substitute",
    (value) => ({ nominee_user_id: value.nominee_user_id }),
  );
}

export function useSubmitAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (value: { id: number; body: Record<string, unknown> }) =>
      (await http.post(ROOT + "/applications/" + value.id + "/actions",
        value.body)).data,
    onSuccess: () => invalidate(client),
  });
}

export function useReplaceActionSubstitute() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (value: { id: number; nominee_user_id: number }) =>
      (await http.post<ActionRequest>(ROOT + "/actions/" + value.id + "/substitute",
        { nominee_user_id: value.nominee_user_id })).data,
    onSuccess: () => invalidate(client),
  });
}

export function useWithdrawAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      (await http.post<ActionRequest>(ROOT + "/actions/" + id + "/withdraw", {})).data,
    onSuccess: () => invalidate(client),
  });
}

export function useTaskDecision() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (value: { id: number; decision: string; note?: string }) =>
      (await http.post(ROOT + "/tasks/" + value.id + "/decision", {
        decision: value.decision,
        note: value.note || "",
      })).data,
    onSuccess: () => invalidate(client),
  });
}

export function useSubstituteResponse() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (value: { id: number; accept: boolean; note?: string }) =>
      (await http.post(ROOT + "/tasks/" + value.id + "/substitute-response", {
        accept: value.accept,
        note: value.note || "",
      })).data,
    onSuccess: () => invalidate(client),
  });
}

export function useMarkNotificationRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      (await http.post(ROOT + "/notifications/" + id + "/read", { read: true })).data,
    onSuccess: () => invalidate(client),
  });
}

export function useAdminPost<T = unknown>(endpoint: string) {
  return usePost<T>(endpoint);
}

export function usePublishCalendar() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      (await http.post(ROOT + "/admin/calendars/" + id + "/publish", {})).data,
    onSuccess: () => invalidate(client),
  });
}

export function useAdminList<T = unknown>(endpoint: string, key: string) {
  return useQuery({
    queryKey: [KEY, "admin", key],
    queryFn: async () => (await http.get<T>(ROOT + endpoint)).data,
  });
}

export async function exportApplication(id: number) {
  return http.get(ROOT + "/applications/" + id + "/export", {
    responseType: "blob",
  });
}
