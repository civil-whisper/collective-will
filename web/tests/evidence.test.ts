import {describe, expect, it} from "vitest";

import {type EvidenceEntry, canonicalJson, verifyChain} from "../lib/evidence";

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
    entry.hash = await sha256Hex(canonicalJson(material));
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

describe("canonicalJson", () => {
  it("sorts keys recursively to match Python json.dumps(sort_keys=True)", () => {
    expect(canonicalJson({b: 1, a: 2})).toBe('{"a":2,"b":1}');
  });

  it("sorts nested object keys", () => {
    const obj = {z: {b: 2, a: 1}, a: "x"};
    expect(canonicalJson(obj)).toBe('{"a":"x","z":{"a":1,"b":2}}');
  });

  it("handles arrays without sorting their elements", () => {
    expect(canonicalJson({b: [3, 1, 2], a: "x"})).toBe('{"a":"x","b":[3,1,2]}');
  });

  it("handles null, booleans, and numbers", () => {
    expect(canonicalJson(null)).toBe("null");
    expect(canonicalJson(true)).toBe("true");
    expect(canonicalJson(42)).toBe("42");
    expect(canonicalJson("hi")).toBe('"hi"');
  });

  it("produces Python-compatible hash for a realistic evidence entry", async () => {
    const material = {
      timestamp: "2026-02-20T10:00:00.000Z",
      event_type: "user_verified",
      entity_type: "user",
      entity_id: "550e8400-e29b-41d4-a716-446655440000",
      payload: {role: "voter", email: "test@example.com"},
      prev_hash: "genesis",
    };
    const serialized = canonicalJson(material);
    expect(serialized).toContain('"email":"test@example.com"');
    expect(serialized).toContain('"role":"voter"');
    expect(serialized.indexOf('"email"')).toBeLessThan(serialized.indexOf('"role"'));

    const hash = await sha256Hex(serialized);
    expect(hash).toHaveLength(64);
  });
});
