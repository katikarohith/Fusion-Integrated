import { useState } from "react";
import {
  Alert, Button, Card, Checkbox, Container, Group, Select, Stack, Text,
  TextInput, Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { errorMessage } from "../../../lib/http";
import { ErrorState } from "../../../ui/components/ErrorState";
import { PageHeader } from "../../../ui/components/PageHeader";
import { useApplyLeave, useLeaveTypes } from "../api/hooks";

export default function ApplyPage() {
  const types = useLeaveTypes();
  const apply = useApplyLeave();
  const [typeId, setTypeId] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [part, setPart] = useState<string | null>("full");
  const [reason, setReason] = useState("");
  const [station, setStation] = useState(false);
  const [stationDetails, setStationDetails] = useState("");
  const [medical, setMedical] = useState("");
  const [substitute, setSubstitute] = useState("");

  if (types.error) return <Container size="md"><ErrorState error={types.error} /></Container>;
  function submit() {
    if (!typeId || !start || !end || !part) return;
    apply.mutate({
      leave_type_id: Number(typeId), start_date: start, end_date: end,
      day_part: part, reason, station_leave_required: station,
      station_leave_details: stationDetails, medical_evidence_reference: medical,
      substitute_user_id: substitute ? Number(substitute) : null,
    }, {
      onSuccess: () => {
        notifications.show({ title: "Leave request submitted", message: "Your request is now in the configured approval workflow.", color: "green" });
        setReason(""); setStart(""); setEnd(""); setStationDetails(""); setMedical(""); setSubstitute("");
      },
      onError: (e) => notifications.show({ title: "Could not submit request", message: errorMessage(e), color: "red" }),
    });
  }

  return (
    <Container size="md">
      <PageHeader title="Apply for Leave" subtitle="Eligibility, calendar rules, balance, and route are checked by the server." />
      <Card padding="lg" withBorder>
        <Stack>
          {apply.error && <Alert color="red">{errorMessage(apply.error)}</Alert>}
          <Select label="Leave category" placeholder="Choose a category" required
            data={(types.data ?? []).map((x) => ({ value: String(x.id), label: x.code + " — " + x.name }))}
            value={typeId} onChange={setTypeId} />
          <Group grow>
            <TextInput type="date" label="Start date" required value={start} onChange={(e) => setStart(e.currentTarget.value)} />
            <TextInput type="date" label="End date" required value={end} onChange={(e) => setEnd(e.currentTarget.value)} />
          </Group>
          <Select label="Day part" data={[{ value: "full", label: "Full day" }, { value: "first_half", label: "First half" }, { value: "second_half", label: "Second half" }]} value={part} onChange={setPart} />
          <Textarea label="Purpose / reason" required minRows={3} value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
          <Checkbox label="Station Leave is required" checked={station} onChange={(e) => setStation(e.currentTarget.checked)} />
          {station && <Textarea label="Station Leave details" required value={stationDetails} onChange={(e) => setStationDetails(e.currentTarget.value)} />}
          <TextInput label="Medical evidence reference" description="Required only when the configured policy asks for it." value={medical} onChange={(e) => setMedical(e.currentTarget.value)} />
          <TextInput label="Substitute employee user ID" description="Required only when the configured route requires substitute consent." inputMode="numeric" value={substitute} onChange={(e) => setSubstitute(e.currentTarget.value)} />
          <Text size="sm" c="dimmed">The published calendar, current account balance, and configured approval route determine whether the request can proceed.</Text>
          <Group justify="flex-end"><Button onClick={submit} loading={apply.isPending} disabled={!typeId || !start || !end || !reason.trim() || (station && !stationDetails.trim())}>Submit request</Button></Group>
        </Stack>
      </Card>
    </Container>
  );
}
