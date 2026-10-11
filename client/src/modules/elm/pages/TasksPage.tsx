import { Alert, Button, Card, Container, Group, Stack, Text, Textarea } from "@mantine/core";
import { useState } from "react";
import { notifications } from "@mantine/notifications";
import { errorMessage } from "../../../lib/http";
import { ErrorState } from "../../../ui/components/ErrorState";
import { PageHeader } from "../../../ui/components/PageHeader";
import { useSubstituteResponse, useTaskDecision, useTasks } from "../api/hooks";
import type { Task } from "../api/types";

function options(task: Task) {
  if (task.kind === "unit_head_recommendation") return ["recommend", "not_recommend"];
  if (task.kind === "establishment") return ["forward"];
  return ["approve", "reject"];
}
export default function TasksPage() {
  const tasks = useTasks();
  const decision = useTaskDecision();
  const substitute = useSubstituteResponse();
  const [notes, setNotes] = useState<Record<number, string>>({});
  if (tasks.error) return <Container size="xl"><ErrorState error={tasks.error} /></Container>;
  function act(task: Task, action: string) {
    const common = { onSuccess: () => notifications.show({ title: "Response recorded", message: "The next configured workflow step is activated.", color: "green" }), onError: (e: unknown) => notifications.show({ title: "Could not complete task", message: errorMessage(e), color: "red" }) };
    if (task.kind === "substitute") substitute.mutate({ id: task.id, accept: action === "accept", note: notes[task.id] ?? "" }, common);
    else decision.mutate({ id: task.id, decision: action, note: notes[task.id] ?? "" }, common);
  }
  return (
    <Container size="xl">
      <PageHeader title="Workflow Tasks" subtitle="Only tasks currently assigned to your account are shown." />
      <Stack>
        {(tasks.data?.results ?? []).map((task) => (
          <Card key={task.id} withBorder padding="lg">
            <Stack>
              <Group justify="space-between"><Text fw={700}>{task.leave_type_code} · {task.action_kind.replaceAll("_", " ")}</Text><Text size="sm" c="dimmed">{task.assignee_role} · employee ID {task.employee_user_id}</Text></Group>
              <Text size="sm">{task.kind.replaceAll("_", " ")} {task.due_at ? "· due " + new Date(task.due_at).toLocaleString() : ""}</Text>
              <Textarea label={task.kind === "substitute" ? "Response note" : "Decision note (required for rejection)"} value={notes[task.id] ?? ""} onChange={(e) => setNotes({ ...notes, [task.id]: e.currentTarget.value })} />
              <Group justify="flex-end">{(task.kind === "substitute" ? ["accept", "decline"] : options(task)).map((action) => <Button key={action} variant={action === "reject" || action === "decline" || action === "not_recommend" ? "light" : "filled"} color={action === "reject" || action === "decline" || action === "not_recommend" ? "red" : "blue"} loading={decision.isPending || substitute.isPending} disabled={action === "reject" && !(notes[task.id] ?? "").trim()} onClick={() => act(task, action)}>{action.replaceAll("_", " ")}</Button>)}</Group>
            </Stack>
          </Card>
        ))}
        {!tasks.data?.results.length && !tasks.isPending && <Alert color="gray">No pending ELM tasks are assigned to you.</Alert>}
      </Stack>
    </Container>
  );
}
