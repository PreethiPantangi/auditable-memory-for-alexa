import { CheckCircle2, AlertCircle, ArrowUpRight, Info } from "lucide-react";

import type { ChatAction } from "../../types/chat";

interface Props {
  action: ChatAction;
  onViewMemory: (memoryKey: string, claimId?: string | null) => void;
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
  forget: "Memory deactivated",
  explain: "Memory source retrieved",
  memory_history: "Memory history retrieved",
};

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

function unwrapData(data: unknown): unknown {
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

function extractMemoryTargets(data: unknown, intent: string): MemoryTarget[] {
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

export default function MemoryActionCard({ action, onViewMemory }: Props) {
  const intent = (action.intent ?? "").toLowerCase();

  const result = action.result;

  const success = result?.success === true;

  const errorCode = result?.error?.code ?? "";

  const isConflict = errorCode.toUpperCase() === "CONFLICTING_MEMORIES";

  const isClarification =
    intent === "clarification_required" ||
    ["CLARIFICATION_REQUIRED", "AMBIGUOUS_MEMORY"].includes(
      errorCode.toUpperCase(),
    );

  const isRecall = intent === "recall";
  const isForget = intent === "forget";

  const payload = unwrapData(result?.data);

  const isEmptyRecall =
    isRecall &&
    success &&
    (payload === null ||
      payload === undefined ||
      (Array.isArray(payload) && payload.length === 0));

  const recallFailed =
    isRecall && result?.success === false && !isClarification && !isConflict;

  const actionFailed = !success && !isClarification && !isConflict;

  const forgetSucceeded = isForget && success;

  const forgetFailed =
    isForget && result?.success === false && !isClarification;

  const isNeutral = isEmptyRecall;

  const title = isConflict
    ? "Conflicting memories found"
    : isClarification
      ? "Clarification needed"
      : isEmptyRecall
        ? "No active memory found"
        : recallFailed
          ? "Unable to retrieve memory"
          : forgetFailed
            ? "Unable to forget memory"
            : actionFailed
              ? "Memory operation failed"
              : (actionTitles[intent] ?? "Memory operation completed");

  const categoryLabel =
    typeof action.category === "string" && action.category.trim()
      ? action.category.replaceAll("_", " ")
      : "Memory not identified";

  const targets =
    (success || isConflict) && !isClarification && !isEmptyRecall
      ? extractMemoryTargets(result?.data, intent)
      : [];

  const statusClasses = isConflict
    ? "border-amber-200 bg-amber-50"
    : isClarification
      ? "border-amber-200 bg-amber-50"
      : actionFailed
        ? "border-red-200 bg-red-50"
        : isNeutral
          ? "border-slate-200 bg-slate-50"
          : "border-slate-200 bg-white";

  return (
    <div
      className={`mt-3 rounded-xl border p-3 ${statusClasses}`}
      role="status"
    >
      <div className="flex items-center gap-2">
        {isConflict || isClarification ? (
          <AlertCircle
            size={18}
            className="shrink-0 text-amber-600"
            aria-hidden="true"
          />
        ) : isNeutral ? (
          <Info
            size={18}
            className="shrink-0 text-slate-500"
            aria-hidden="true"
          />
        ) : actionFailed ? (
          <AlertCircle
            size={18}
            className="shrink-0 text-red-600"
            aria-hidden="true"
          />
        ) : (
          <CheckCircle2
            size={18}
            className="shrink-0 text-emerald-600"
            aria-hidden="true"
          />
        )}

        <span className="text-sm font-semibold text-slate-800">{title}</span>
      </div>

      <p className="mt-2 text-xs capitalize text-slate-500">{categoryLabel}</p>

      {isConflict && (
        <p className="mt-2 text-xs leading-5 text-amber-800">
          Multiple saved memories contain conflicting information. No memory was
          changed. You can inspect their histories below.
        </p>
      )}

      {/* Clarification required */}
      {isClarification && (
        <div className="mt-2 rounded-lg bg-amber-100/60 p-3">
          <p className="text-xs text-amber-900">
            {result?.error?.message ?? "Please clarify which memory you mean."}
          </p>

          <p className="mt-1 text-xs text-amber-700">
            No memory was saved or changed.
          </p>
        </div>
      )}

      {/* Empty recall */}
      {isEmptyRecall && (
        <p className="mt-2 text-xs text-slate-600">
          No active memory matches this request.
        </p>
      )}

      {/* Successful forget */}
      {forgetSucceeded && (
        <p className="mt-2 text-xs leading-5 text-slate-600">
          This memory will no longer be used for active recall. Its history
          remains available for auditing.
        </p>
      )}

      {/* Failed operation */}
      {actionFailed && (
        <p className="mt-2 text-xs text-red-700">
          {result?.error?.message ??
            "The memory operation could not be completed."}
        </p>
      )}

      {/* Memory history navigation */}
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
              onClick={() => onViewMemory(target.memoryKey, target.claimId)}
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-left text-xs font-medium text-blue-700 transition-colors hover:bg-blue-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            >
              <span className="min-w-0 wrap-break-word">
                {targets.length === 1 ? "View memory history" : target.label}
              </span>

              <ArrowUpRight size={15} className="shrink-0" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
