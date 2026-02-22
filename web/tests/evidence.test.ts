import {describe, expect, it} from "vitest";

import {type EvidenceEntry, verifyChain} from "../lib/evidence";

async function sha256Hex(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function buildChain(count: number): Promise<EvidenceEntry[]> {
  const entries: EvidenceEntry[] = [];
  let prevHash = "genesis";
  for (let i = 0; i < count; i++) {
    const entry = {
      timestamp: `2026-02-20T10:0${i}:00.000Z`,
      event_type: "test_event",
      entity_type: "test",
      entity_id: `entity-${i}`,
      payload: {index: i},
      prev_hash: prevHash,
      hash: "",
    };
    const material = {
      timestamp: entry.timestamp,
      event_type: entry.event_type,
      entity_type: entry.entity_type,
      entity_id: entry.entity_id.toLowerCase(),
      payload: entry.payload,
      prev_hash: entry.prev_hash,
    };
    entry.hash = await sha256Hex(JSON.stringify(material, Object.keys(material).sort()));
    entries.push(entry);
    prevHash = entry.hash;
  }
  return entries;
}

describe("verifyChain", () => {
  it("returns valid for correct chain", async () => {
    const entries = await buildChain(3);
    const result = await verifyChain(entries);
    expect(result.valid).toBe(true);
  });

  it("returns invalid when hash is tampered", async () => {
    const entries = await buildChain(3);
    entries[1].hash = "tampered";
    const result = await verifyChain(entries);
    expect(result.valid).toBe(false);
    expect(result.failedIndex).toBe(1);
  });

  it("returns invalid when prev_hash chain is broken", async () => {
    const entries = await buildChain(3);
    entries[2].prev_hash = "broken";
    const result = await verifyChain(entries);
    expect(result.valid).toBe(false);
    expect(result.failedIndex).toBe(2);
  });

  it("returns invalid when event_type is tampered", async () => {
    const entries = await buildChain(2);
    entries[0].event_type = "tampered";
    const result = await verifyChain(entries);
    expect(result.valid).toBe(false);
    expect(result.failedIndex).toBe(0);
  });

  it("returns invalid when entity_type is tampered", async () => {
    const entries = await buildChain(2);
    entries[0].entity_type = "tampered";
    const result = await verifyChain(entries);
    expect(result.valid).toBe(false);
    expect(result.failedIndex).toBe(0);
  });

  it("returns invalid when entity_id is tampered", async () => {
    const entries = await buildChain(2);
    entries[0].entity_id = "TAMPERED-ID";
    const result = await verifyChain(entries);
    expect(result.valid).toBe(false);
    expect(result.failedIndex).toBe(0);
  });

  it("returns invalid when timestamp is tampered", async () => {
    const entries = await buildChain(2);
    entries[0].timestamp = "2099-01-01T00:00:00.000Z";
    const result = await verifyChain(entries);
    expect(result.valid).toBe(false);
    expect(result.failedIndex).toBe(0);
  });

  it("returns valid for empty chain", async () => {
    const result = await verifyChain([]);
    expect(result.valid).toBe(true);
  });

  it("returns valid for single valid entry", async () => {
    const entries = await buildChain(1);
    const result = await verifyChain(entries);
    expect(result.valid).toBe(true);
  });
});
