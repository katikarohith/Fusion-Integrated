import { useState } from "react";
import {
  Alert, Button, Card, Container, Group, Select, SimpleGrid, Stack, Text,
  TextInput, Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { errorMessage } from "../../../lib/http";
import { ErrorState } from "../../../ui/components/ErrorState";
import { PageHeader } from "../../../ui/components/PageHeader";
import { exportApplication, useApplications, useActions, useSubmitAction, useWithdrawLeave, useReplaceSubstitute, useReplaceActionSubstitute, useWithdrawAction } from "../api/hooks";
import type { Application } from "../api/types";

const canWithdraw = new Set(["awaiting_substitute", "applicant_action_required", "pending_approval"]);

export default function MyLeavePage() {
  const apps = useApplications();
  const actions = useActions();
  const withdraw = useWithdrawLeave();
  const replace = useReplaceSubstitute();
  const submitAction = useSubmitAction();
  const replaceAction = useReplaceActionSubstitute();
  const withdrawAction = useWithdrawAction();
  const [replacement, setReplacement] = useState<Record<number, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [kind, setKind] = useState<string | null>("cancellation");
  const [reason, setReason] = useState("");
  const [requestedEnd, setRequestedEnd] = useState("");
  const [resumption, setResumption] = useState("");
  const [medical, setMedical] = useState("");
  const [nominee, setNominee] = useState("");
  const [replacementAction, setReplacementAction] = useState<Record<number, string>>({});

  if (apps.error) return <Container size="xl"><ErrorState error={apps.error} /></Container>;
  if (actions.error) return <Container size="xl"><ErrorState error={actions.error} /></Container>;
  const rows = apps.data?.results ?? [];
  const approved = rows.filter((app) => app.status === "approved");
  function doWithdraw(app: Application) {
    withdraw.mutate(app.id, {
      onSuccess: () => notifications.show({ title: "Request withdrawn", message: "The reservation was released.", color: "green" }),
      onError: (e) => notifications.show({ title: "Could not withdraw", message: errorMessage(e), color: "red" }),
    });
  }
  function doReplace(app: Application) {
    const value = Number(replacement[app.id]);
    if (!value) return;
    replace.mutate({ id: app.id, nominee_user_id: value }, {
      onSuccess: () => notifications.show({ title: "Substitute requested", message: "The new nominee must accept before approval routing continues.", color: "green" }),
      onError: (e) => notifications.show({ title: "Could not nominate substitute", message: errorMessage(e), color: "red" }),
    });
  }
  function doAction() {
    const appId = Number(selected);
    if (!appId || !kind) return;
    const body: Record<string, unknown> = { kind, reason };
    if (kind === "extension") {
      body.requested_end_date = requestedEnd;
      body.substitute_user_id = nominee ? Number(nominee) : null;
      body.medical_evidence_reference = medical;
    }
    if (kind === "resumption") body.actual_resumption_date = resumption;
    submitAction.mutate({ id: appId, body }, {
      onSuccess: () => { notifications.show({ title: "Change request submitted", message: "It is awaiting the configured review workflow.", color: "green" }); setReason(""); },
      onError: (e) => notifications.show({ title: "Could not submit change", message: errorMessage(e), color: "red" }),
    });
  }
  function replaceActionSubstitute(actionId: number) {
    const userId = Number(replacementAction[actionId]);
    if (!userId) return;
    replaceAction.mutate({ id: actionId, nominee_user_id: userId }, {
      onSuccess: () => notifications.show({ title: "Replacement nominated", message: "The extension returns to the substitute consent step.", color: "green" }),
      onError: (e) => notifications.show({ title: "Could not nominate replacement", message: errorMessage(e), color: "red" }),
    });
  }
  function withdrawPendingAction(actionId: number) {
    withdrawAction.mutate(actionId, {
      onSuccess: () => notifications.show({ title: "Change request withdrawn", message: "The pending action was withdrawn.", color: "green" }),
      onError: (e) => notifications.show({ title: "Could not withdraw change", message: errorMessage(e), color: "red" }),
    });
  }  async function download(app: Application) {
    try {
      const response = await exportApplication(app.id);
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url; link.download = "leave-application-" + app.id + ".csv";
      link.click(); URL.revokeObjectURL(url);
    } catch (e) {
      notifications.show({ title: "Could not export application", message: errorMessage(e), color: "red" });
    }
  }

  return (
    <Container size="xl">
      <PageHeader title="My Leave" subtitle="Track requests and submit permitted changes." />
      <Stack>
        {!rows.length && !apps.isPending && <Alert color="gray">No leave requests yet.</Alert>}
        {rows.map((app) => (
          <Card key={app.id} withBorder padding="md">
            <Stack gap="sm">
              <Group justify="space-between" align="flex-start">
                <div><Text fw={700}>{app.leave_type_code} — {app.leave_type_name}</Text><Text size="sm" c="dimmed">{app.start_date} to {app.end_date} · {app.days} day(s) · {app.day_part.replace("_", " ")}</Text></div>
                <Text fw={600} tt="capitalize">{app.status.replaceAll("_", " ")}</Text>
              </Group>
              <Text size="sm">{app.reason}</Text>
              {app.station_leave_required && <Text size="sm" c="dimmed">Station Leave: {app.station_leave_details}</Text>}
              {app.origin === "offline" && <Text size="sm" c="dimmed">Offline sanction reference: {app.offline_reference}</Text>}
              <Group>
                <Button variant="default" size="xs" onClick={() => void download(app)}>Export CSV</Button>
                {canWithdraw.has(app.status) && <Button color="red" variant="light" size="xs" loading={withdraw.isPending} onClick={() => doWithdraw(app)}>Withdraw</Button>}
              </Group>
              {app.status === "applicant_action_required" && app.substitute_required && (
                <Group align="flex-end"><TextInput label="Replacement substitute user ID" inputMode="numeric" value={replacement[app.id] ?? ""} onChange={(e) => setReplacement({ ...replacement, [app.id]: e.currentTarget.value })} /><Button size="sm" onClick={() => doReplace(app)} loading={replace.isPending}>Nominate replacement</Button></Group>
              )}
            </Stack>
          </Card>
        ))}
        {(actions.data?.results ?? []).length > 0 && <Card withBorder padding="lg">
          <Stack><Text fw={700}>Change requests</Text>
            {(actions.data?.results ?? []).map((action) => <Card key={action.id} withBorder padding="sm">
              <Stack gap="xs"><Group justify="space-between"><Text fw={600}>{action.kind} · request #{action.id}</Text><Text tt="capitalize">{action.status.replaceAll("_", " ")}</Text></Group>
                <Text size="sm" c="dimmed">Application #{action.application_id}{action.requested_end_date ? " · requested through " + action.requested_end_date : ""}{action.actual_resumption_date ? " · resumed " + action.actual_resumption_date : ""}</Text>
                {action.status === "applicant_action_required" && action.kind === "extension" && <Group align="flex-end"><TextInput label="Replacement substitute user ID" inputMode="numeric" value={replacementAction[action.id] ?? ""} onChange={(e) => setReplacementAction({ ...replacementAction, [action.id]: e.currentTarget.value })} /><Button size="sm" onClick={() => replaceActionSubstitute(action.id)} loading={replaceAction.isPending}>Nominate replacement</Button></Group>}
                {["awaiting_substitute", "applicant_action_required", "pending_approval"].includes(action.status) && <Group justify="flex-end"><Button size="xs" color="red" variant="light" loading={withdrawAction.isPending} onClick={() => withdrawPendingAction(action.id)}>Withdraw change request</Button></Group>}
              </Stack>
            </Card>)}
          </Stack>
        </Card>}
        {approved.length > 0 && <Card withBorder padding="lg">
          <Stack>
            <Text fw={700}>Request a change to approved leave</Text>
            <Select label="Leave request" data={approved.map((a) => ({ value: String(a.id), label: a.leave_type_code + " · " + a.start_date + " to " + a.end_date }))} value={selected} onChange={setSelected} />
            <Select label="Change type" data={[{ value: "cancellation", label: "Cancel before leave starts" }, { value: "extension", label: "Extend ongoing EL / COL / VL" }, { value: "resumption", label: "Record actual resumption" }]} value={kind} onChange={setKind} />
            {kind === "extension" && <SimpleGrid cols={{ base: 1, sm: 2 }}><TextInput type="date" label="Requested new end date" value={requestedEnd} onChange={(e) => setRequestedEnd(e.currentTarget.value)} /><TextInput label="Substitute user ID, if route requires one" inputMode="numeric" value={nominee} onChange={(e) => setNominee(e.currentTarget.value)} /><TextInput label="Medical evidence reference" value={medical} onChange={(e) => setMedical(e.currentTarget.value)} /></SimpleGrid>}
            {kind === "resumption" && <TextInput type="date" label="Actual resumption date" value={resumption} onChange={(e) => setResumption(e.currentTarget.value)} />}
            <Textarea label="Reason / review note" required value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
            {submitAction.error && <Alert color="red">{errorMessage(submitAction.error)}</Alert>}
            <Group justify="flex-end"><Button loading={submitAction.isPending} disabled={!selected || !kind || !reason.trim() || (kind === "extension" && !requestedEnd) || (kind === "resumption" && !resumption)} onClick={doAction}>Submit change request</Button></Group>
          </Stack>
        </Card>}
      </Stack>
    </Container>
  );
}
