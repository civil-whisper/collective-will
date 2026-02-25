import {DisputeStatus} from "@/components/DisputeStatus";
import {PageShell, Card} from "@/components/ui";

export default function DisputesPage() {
  return (
    <PageShell title="Disputes">
      <Card>
        <DisputeStatus status="open" />
      </Card>
    </PageShell>
  );
}
