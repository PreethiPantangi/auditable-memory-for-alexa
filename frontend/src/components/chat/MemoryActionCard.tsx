
import {
  CheckCircle2,
  AlertCircle,
  History,
  ArrowUpRight,
} from "lucide-react";

import type { ChatAction } from "../../types/chat";

interface Props {
  action: ChatAction;
  onViewMemory: (
    memoryKey: string,
    claimId?: string | null
  ) => void;
}

interface MemoryTarget {
  memoryKey: string;
  claimId: string | null;
  label: string;
}

const actionTitles: Record<string, string> = {
  remember: "Memory saved",
  recall: "Memory retrieved",
  correct_memory: "Memory updated",
  forget: "Memory forgotten",
  explain: "Memory source retrieved",
  memory_history: "Memory history retrieved",
};

function isRecord(
  value: unknown
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function readString(
  record: Record<string, unknown>,
  key: string
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

function unwrapData(data: unknown): unknown {
  if (isRecord(data) && "data" in data) {
    return data.data;
  }

  return data;
}

function toMemoryTarget(
  item: unknown,
  intent: string
): MemoryTarget | null {
  if (!isRecord(item)) return null;

  const claim = isRecord(item.new_claim)
    ? item.new_claim
    : isRecord(item.claim)
      ? item.claim
      : item;

  const memoryKey =
    readString(item, "memory_key") ??
    readString(claim, "memory_key");

  if (!memoryKey) return null;

  const claimId =
    (intent === "correct_memory"
      ? readString(item, "new_claim_id")
      : null) ??
    readString(item, "claim_id") ??
    readString(claim, "claim_id") ??
    readString(claim, "id");

  const label =
    readString(claim, "value") ??
    readString(item, "value") ??
    memoryKey;

  return {
    memoryKey,
    claimId,
    label,
  };
}

function extractMemoryTargets(
  data: unknown,
  intent: string
): MemoryTarget[] {
  const payload = unwrapData(data);

  const items: unknown[] = Array.isArray(payload)
    ? payload
    : [payload];

  const targetMap = new Map<string, MemoryTarget>();

  for (const item of items) {
    const target = toMemoryTarget(item, intent);

    if (!target) continue;

    // One logical memory per button.
    // Prefer the ACTIVE version when processing arrays.
    const existing = targetMap.get(target.memoryKey);

    if (!existing) {
      targetMap.set(target.memoryKey, target);
    } else if (intent === "memory_history") {
      // A history result may contain multiple claim versions.
      // Do not arbitrarily highlight a historical version.
      targetMap.set(target.memoryKey, {
        ...target,
        claimId: null,
      });
    }
  }

  return Array.from(targetMap.values());
}

export default function MemoryActionCard({
  action,
  onViewMemory,
}: Props) {
  const intent = (action.intent ?? "").toLowerCase();

  const success = action.result?.success === true;

  const isClarification =
  ["CLARIFICATION_REQUIRED", "AMBIGUOUS_MEMORY"].includes(
    action.result?.error?.code ?? ""
  ) ||
  intent === "clarification_required";

  const title = isClarification
    ? "Clarification needed"
    : success
      ? actionTitles[intent] ??
        "Memory operation completed"
      : "Memory operation failed";

  const categoryLabel =
    typeof action.category === "string" &&
    action.category.trim()
      ? action.category.replaceAll("_", " ")
      : "Memory not identified";

  const targets =
    success && !isClarification
      ? extractMemoryTargets(action.result?.data, intent)
      : [];

  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-2">
        {isClarification ? (
          <History size={18} className="text-amber-600" />
        ) : success ? (
          <CheckCircle2
            size={18}
            className="text-emerald-600"
          />
        ) : (
          <AlertCircle
            size={18}
            className="text-red-600"
          />
        )}

        <span className="text-sm font-semibold text-slate-800">
          {title}
        </span>
      </div>

      <p className="mt-2 text-xs capitalize text-slate-500">
        {categoryLabel}
      </p>

      {isClarification && (
        <div className="mt-2 rounded-lg bg-amber-50 p-3">
          <p className="text-xs text-amber-900">
            {action.result?.error?.message ??
              "Please clarify which memory you mean."}
          </p>
          <p className="mt-1 text-xs text-amber-700">
            No memory was saved or changed.
          </p>
        </div>
      )}

      {!success &&
        !isClarification &&
        action.result?.error && (
          <p className="mt-2 text-xs text-red-600">
            {action.result.error.message}
          </p>
        )}

      {targets.length > 0 && (
        <div className="mt-3 space-y-2">
          {targets.length > 1 && (
            <p className="text-xs font-medium text-slate-500">
              View history for:
            </p>
          )}

          {targets.map((target) => (
            <button
              key={target.memoryKey}
              type="button"
              onClick={() =>
                onViewMemory(
                  target.memoryKey,
                  target.claimId
                )
              }
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-left text-xs font-medium text-blue-700 hover:bg-blue-100 focus-visible:outline-2 focus-visible:outline-blue-600"
            >
              <span className="min-w-0 break-words">
                {targets.length === 1
                  ? "View memory history"
                  : target.label}
              </span>

              <ArrowUpRight
                size={15}
                className="shrink-0"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
