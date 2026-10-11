import { Card, Container, Group, Stack, Table, Text } from "@mantine/core";
import { FaChartBar } from "react-icons/fa";
import { ErrorState } from "../../../ui/components/ErrorState";
import { PageHeader } from "../../../ui/components/PageHeader";
import { useBalances, useHistory } from "../api/hooks";
import type { Balance, LedgerEntry } from "../api/types";

export default function BalancesPage() {
  const balances = useBalances();
  const history = useHistory();
  if (balances.error) return <Container size="xl"><ErrorState error={balances.error} /></Container>;
  if (history.error) return <Container size="xl"><ErrorState error={history.error} /></Container>;
  return (
    <Container size="xl">
      <PageHeader title="Balances and History" subtitle="Account values are maintained in the server ledger." />
      <Stack>
        <Card withBorder padding="lg">
          <Text fw={700} mb="sm">Annual balances</Text>
          <Table.ScrollContainer minWidth={760}><Table striped highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Year</Table.Th><Table.Th>Category</Table.Th><Table.Th>Allotted</Table.Th><Table.Th>Carry</Table.Th><Table.Th>Used</Table.Th><Table.Th>Reserved</Table.Th><Table.Th>Available</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{(balances.data?.results ?? []).map((b: Balance) => <Table.Tr key={b.id}><Table.Td>{b.year}</Table.Td><Table.Td>{b.leave_type_code} — {b.leave_type_name}</Table.Td><Table.Td>{b.allotted}</Table.Td><Table.Td>{b.carried_forward}</Table.Td><Table.Td>{b.used}</Table.Td><Table.Td>{b.reserved}</Table.Td><Table.Td fw={700}>{b.available}</Table.Td></Table.Tr>)}</Table.Tbody>
          </Table></Table.ScrollContainer>
          {!balances.data?.results.length && !balances.isPending && <Text c="dimmed" size="sm" mt="sm">Your balances appear when a leave request initializes an account.</Text>}
        </Card>
        <Card withBorder padding="lg">
          <Group mb="sm"><FaChartBar /><Text fw={700}>Account history</Text></Group>
          <Table.ScrollContainer minWidth={720}><Table striped>
            <Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Year</Table.Th><Table.Th>Category</Table.Th><Table.Th>Entry</Table.Th><Table.Th>Amount</Table.Th><Table.Th>Reason</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{(history.data?.results ?? []).map((entry: LedgerEntry) => <Table.Tr key={entry.id}><Table.Td>{new Date(entry.created_at).toLocaleDateString()}</Table.Td><Table.Td>{entry.year}</Table.Td><Table.Td>{entry.leave_type_code}</Table.Td><Table.Td>{entry.kind}</Table.Td><Table.Td>{entry.amount}</Table.Td><Table.Td>{entry.reason}</Table.Td></Table.Tr>)}</Table.Tbody>
          </Table></Table.ScrollContainer>
        </Card>
      </Stack>
    </Container>
  );
}
