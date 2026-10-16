interface MemoryTarget {
  memoryKey: string;
  claimId: string | null;
  label: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(
  record: Record<string, unknown>,
  key: string,
): string | null {
  const value = record[key];

  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }

  if (typeof value === "string" && value.trim()) {
    return value;
  }

  return null;
}

export function unwrapData(data: unknown): unknown {
  let current = data;

  // Support nested MCP/API data wrappers.
  for (let i = 0; i < 3; i++) {
    if (!isRecord(current) || !("data" in current)) {
      break;
    }

    current = current.data;
  }

  return current;
}

function toMemoryTarget(item: unknown, intent: string): MemoryTarget | null {
  if (!isRecord(item)) return null;

  const claim = isRecord(item.new_claim)
    ? item.new_claim
    : isRecord(item.claim)
      ? item.claim
      : item;

  const memoryKey =
    readString(item, "memory_key") ?? readString(claim, "memory_key");

  if (!memoryKey) return null;

  const claimId =
    (intent === "correct_memory" ? readString(item, "new_claim_id") : null) ??
    readString(item, "claim_id") ??
    readString(claim, "claim_id") ??
    readString(claim, "id");

  const label =
    readString(claim, "value") ?? readString(item, "value") ?? memoryKey;

  return {
    memoryKey,
    claimId,
    label,
  };
}

export function extractMemoryTargets(
  data: unknown,
  intent: string,
): MemoryTarget[] {
  const payload = unwrapData(data);

  const items: unknown[] = Array.isArray(payload)
    ? payload
    : isRecord(payload) && Array.isArray(payload.memories)
      ? payload.memories
      : isRecord(payload) && Array.isArray(payload.claims)
        ? payload.claims
        : [payload];

  const targetMap = new Map<string, MemoryTarget>();

  for (const item of items) {
    const target = toMemoryTarget(item, intent);

    if (!target) continue;

    const existing = targetMap.get(target.memoryKey);

    if (!existing) {
      targetMap.set(
        target.memoryKey,
        intent === "memory_history" ? { ...target, claimId: null } : target,
      );
    } else if (intent === "memory_history") {
      // A history response may contain many versions.
      // Do not highlight an arbitrary claim.
      targetMap.set(target.memoryKey, {
        ...existing,
        claimId: null,
      });
    }
  }

  return Array.from(targetMap.values());
}
