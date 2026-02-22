export type EvidenceEntry = {
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  hash: string;
  prev_hash: string;
};

async function sha256Hex(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyChain(entries: EvidenceEntry[]): Promise<{valid: boolean; failedIndex?: number}> {
  let previous = "genesis";
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const material = {
      timestamp: entry.timestamp,
      event_type: entry.event_type,
      entity_type: entry.entity_type,
      entity_id: entry.entity_id.toLowerCase(),
      payload: entry.payload,
      prev_hash: entry.prev_hash
    };
    const serialized = JSON.stringify(material, Object.keys(material).sort());
    const expected = await sha256Hex(serialized);
    if (entry.hash !== expected || entry.prev_hash !== previous) {
      return {valid: false, failedIndex: index};
    }
    previous = entry.hash;
  }
  return {valid: true};
}
