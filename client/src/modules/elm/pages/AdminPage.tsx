import { useState } from "react";
import {
  Alert, Button, Card, Code, Container, Group, Stack, Tabs, Text, Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { errorMessage } from "../../../lib/http";
import { PageHeader } from "../../../ui/components/PageHeader";
import { useAdminList, useAdminPost, usePublishCalendar } from "../api/hooks";

const examples = {
  policy: { endpoint: "/admin/policies", title: "Save entitlement policy", initial: "{\n  \"leave_type_code\": \"CL\",\n  \"employee_kind\": \"staff\",\n  \"annual_entitlement\": \"8.00\",\n  \"carry_forward\": false,\n  \"carry_forward_limit\": null,\n  \"counting_mode\": \"working\",\n  \"requires_medical_evidence\": false,\n  \"requires_vacation_period\": false\n}" },
  profile: { endpoint: "/admin/employee-profiles", title: "Save employee context", initial: "{\n  \"user_id\": 123,\n  \"unit_code\": \"\",\n  \"designation\": \"\",\n  \"is_director\": false\n}" },
  route: { endpoint: "/admin/routes", title: "Create or replace approval route", initial: "{\n  \"leave_type_code\": \"CL\",\n  \"request_kind\": \"leave\",\n  \"employee_kind\": \"staff\",\n  \"unit_code\": \"\",\n  \"designation\": \"\",\n  \"director_applicant\": false,\n  \"requires_substitute\": false,\n  \"steps\": [{\"kind\":\"unit_head_final\",\"assignee_user_id\":123,\"assignee_role\":\"Unit Head\"}]\n}" },
  calendar: { endpoint: "/admin/calendars", title: "Create calendar draft", initial: "{\n  \"year\": 2026,\n  \"name\": \"Academic Calendar 2026\",\n  \"weekly_closed_days\": [5,6],\n  \"dates\": [{\"day\":\"2026-01-26\",\"kind\":\"closed\",\"label\":\"Holiday\"},{\"day\":\"2026-02-12\",\"kind\":\"restricted_holiday\",\"label\":\"RH\"}],\n  \"vacation_periods\": [{\"start_date\":\"2026-05-01\",\"end_date\":\"2026-06-30\",\"label\":\"Summer vacation\",\"source_reference\":\"Academic calendar\"}]\n}" },
  sla: { endpoint: "/admin/sla", title: "Save SLA thresholds", initial: "{\n  \"task_kind\": \"unit_head_final\",\n  \"reminder_after_hours\": 48,\n  \"escalation_after_hours\": 96,\n  \"escalation_user_id\": 123\n}" },
  offline: { endpoint: "/admin/offline-leaves", title: "Synchronize sanctioned offline leave", initial: "{\n  \"employee_user_id\": 123,\n  \"leave_type_code\": \"EL\",\n  \"start_date\": \"2026-01-05\",\n  \"end_date\": \"2026-01-07\",\n  \"day_part\": \"full\",\n  \"reason\": \"Authorized offline record\",\n  \"station_leave_required\": false,\n  \"station_leave_details\": \"\",\n  \"medical_evidence_reference\": \"\",\n  \"sanction_reference\": \"ORDER-123\",\n  \"sanctioned_by_user_id\": 456,\n  \"sanction_date\": \"2026-01-02\"\n}" },
  adjustment: { endpoint: "/admin/balance-adjustments", title: "Adjust a balance with reason", initial: "{\n  \"balance_id\": 1,\n  \"amount\": \"1.00\",\n  \"reason\": \"Documented correction reference\"\n}" },
  yearend: { endpoint: "/admin/year-end", title: "Run year-end processing", initial: "{\n  \"year\": 2025\n}" },
  slaProcess: { endpoint: "/admin/sla/process", title: "Process pending SLA thresholds", initial: "{}" },
};

function JsonOperation({ itemKey }: { itemKey: keyof typeof examples }) {
  const item = examples[itemKey];
  const [text, setText] = useState(item.initial);
  const mutation = useAdminPost(item.endpoint);
  const [response, setResponse] = useState<unknown>(null);
  function submit() {
    try {
      const value = JSON.parse(text) as Record<string, unknown>;
      mutation.mutate(value, {
        onSuccess: (data) => { setResponse(data); notifications.show({ title: "ELM configuration saved", message: item.title, color: "green" }); },
      });
    } catch {
      notifications.show({ title: "Invalid JSON", message: "Correct the request body and try again.", color: "red" });
    }
  }
  return <Stack>
    <Text fw={700}>{item.title}</Text>
    <Text size="sm" c="dimmed">Submit a JSON request body matching the API contract. The server validates policy, calendar, and authority rules.</Text>
    <Textarea aria-label={item.title + " request body"} autosize minRows={8} maxRows={20} value={text} onChange={(e) => setText(e.currentTarget.value)} styles={{ input: { fontFamily: "monospace" } }} />
    {mutation.error && <Alert color="red">{errorMessage(mutation.error)}</Alert>}
    {response != null && <Code block>{JSON.stringify(response, null, 2)}</Code>}
    <Group justify="flex-end"><Button loading={mutation.isPending} onClick={submit}>Submit</Button></Group>
  </Stack>;
}

function CalendarList() {
  const query = useAdminList<unknown>("/admin/calendars", "calendars");
  const publish = usePublishCalendar();
  if (query.error) return <Alert color="red">{errorMessage(query.error)}</Alert>;
  const calendars = Array.isArray(query.data) ? query.data as Array<{ id: number; year: number; name: string; status: string }> : [];
  return <Stack>
    <Text fw={700}>Calendar drafts and published versions</Text>
    {calendars.map((calendar) => <Group key={calendar.id} justify="space-between">
      <Text>{calendar.year} · {calendar.name} · {calendar.status}</Text>
      {calendar.status === "draft" && <Button size="xs" loading={publish.isPending} onClick={() => publish.mutate(calendar.id)}>Publish</Button>}
    </Group>)}
    {publish.error && <Alert color="red">{errorMessage(publish.error)}</Alert>}
  </Stack>;
}
function ReadOnlyList({ endpoint, label, queryKey }: { endpoint: string; label: string; queryKey: string }) {
  const query = useAdminList<unknown>(endpoint, queryKey);
  if (query.error) return <Alert color="red">{errorMessage(query.error)}</Alert>;
  return <Stack><Text fw={700}>{label}</Text><Code block>{JSON.stringify(query.data ?? [], null, 2)}</Code></Stack>;
}

export default function AdminPage() {
  return (
    <Container size="xl">
      <PageHeader title="Leave Configuration" subtitle="Configure policy and routing only from approved institutional rules and current authority data." />
      <Alert color="yellow" title="Operational setup required">
        ELM fails closed when policy, published calendars, or an exact approval route is missing. Populate these from the current Academic Calendar and authorized organization records before opening applications.
      </Alert>
      <Card withBorder padding="lg" mt="md">
        <Tabs defaultValue="policy">
          <Tabs.List grow>
            <Tabs.Tab value="policy">Policies</Tabs.Tab><Tabs.Tab value="profiles">Employee context</Tabs.Tab><Tabs.Tab value="routes">Routes</Tabs.Tab><Tabs.Tab value="calendars">Calendars</Tabs.Tab><Tabs.Tab value="sla">SLA</Tabs.Tab><Tabs.Tab value="records">Records</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="policy" pt="md"><Stack><ReadOnlyList endpoint="/admin/policies" label="Current policies" queryKey="policies" /><JsonOperation itemKey="policy" /></Stack></Tabs.Panel>
          <Tabs.Panel value="profiles" pt="md"><JsonOperation itemKey="profile" /></Tabs.Panel>
          <Tabs.Panel value="routes" pt="md"><Stack><ReadOnlyList endpoint="/admin/routes" label="Current routes" queryKey="routes" /><JsonOperation itemKey="route" /></Stack></Tabs.Panel>
          <Tabs.Panel value="calendars" pt="md"><Stack><CalendarList /><JsonOperation itemKey="calendar" /><Text size="sm" c="dimmed">Include the approved institutional calendar dates and any applicable restricted holidays before publishing.</Text></Stack></Tabs.Panel>
          <Tabs.Panel value="sla" pt="md"><Stack><ReadOnlyList endpoint="/admin/sla" label="Active SLA policies" queryKey="sla" /><JsonOperation itemKey="sla" /><JsonOperation itemKey="slaProcess" /></Stack></Tabs.Panel>
          <Tabs.Panel value="records" pt="md"><Stack><JsonOperation itemKey="offline" /><JsonOperation itemKey="adjustment" /><JsonOperation itemKey="yearend" /></Stack></Tabs.Panel>
        </Tabs>
      </Card>
    </Container>
  );
}
