import {DisputeStatus} from "@/components/DisputeStatus";

export default function DisputesPage() {
  return (
    <section>
      <h1>Disputes</h1>
      <DisputeStatus status="open" />
    </section>
  );
}
