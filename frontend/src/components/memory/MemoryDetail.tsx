import { useEffect, useState } from "react";
import {
  Database,
  CalendarDays,
  Fingerprint,
  Quote,
  History,
} from "lucide-react";

import type { MemoryClaim } from "../../types/memory";
import { getMemoryHistory } from "../../services/memoryApi";
import MemoryTimeline from "./MemoryTimeline";

interface Props {
  userId: string;
  memory: MemoryClaim | null;
  selectedMemoryKey: string | null;
  highlightedClaimId: string | null;
  navigationVersion: number;
}

interface HistoryResult {
  userId: string;
  memoryKey: string;
  history: MemoryClaim[];
  error: string | null;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Unknown date";

  const date = new Date(value);

  return Number.isNaN(date.getTime()) ? "Unknown date" : date.toLocaleString();
}

export default function MemoryDetail({
  userId,
  memory,
  selectedMemoryKey,
  highlightedClaimId,
  navigationVersion,
}: Props) {
  const [historyResult, setHistoryResult] = useState<HistoryResult | null>(
    null,
  );

  // 1. Declare memoryKey BEFORE using it.
  const memoryKey = selectedMemoryKey ?? memory?.memory_key ?? null;

  // 2. Only display results for the selected memory.
  const isCurrentResult =
    historyResult !== null &&
    historyResult.userId === userId &&
    historyResult.memoryKey === memoryKey;

  const history: MemoryClaim[] = isCurrentResult ? historyResult.history : [];

  const error = isCurrentResult ? historyResult.error : null;

  const loading = memoryKey !== null && !isCurrentResult;

  // 3. Fetch asynchronously. No synchronous setState.
  useEffect(() => {
    if (!memoryKey) return;

    let cancelled = false;

    async function loadHistory(key: string) {
      try {
        const result = await getMemoryHistory(userId, key);

        if (!cancelled) {
          setHistoryResult({
            userId,
            memoryKey: key,
            history: result.history ?? [],
            error: null,
          });
        }
      } catch {
        if (!cancelled) {
          setHistoryResult({
            userId,
            memoryKey: key,
            history: [],
            error: "Could not load memory history.",
          });
        }
      }
    }

    void loadHistory(memoryKey);

    return () => {
      cancelled = true;
    };
  }, [memoryKey, userId]);

  // 4. Derive current claim from the history.
  const currentClaim =
    history.find((claim) => claim.status === "ACTIVE") ??
    [...history].sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0] ??
    (memory?.memory_key === memoryKey ? memory : null);

  if (!memoryKey) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <Database size={19} className="text-blue-600" />
          <h2 className="text-lg font-bold">Memory Details</h2>
        </div>

        <p className="mt-3 text-sm text-slate-500">
          Select a memory to inspect its source and correction history.
        </p>
      </section>
    );
  }

  return (
    <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <Database size={19} className="text-blue-600" />
        <h2 className="text-lg font-bold text-slate-900">Memory Details</h2>
      </div>

      {loading && (
        <p role="status" className="mt-4 text-sm text-slate-500">
          Loading memory history...
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      {!loading && !error && currentClaim && (
        <>
          <div className="mt-5 rounded-xl border border-blue-100 bg-blue-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                {currentClaim.status === "ACTIVE"
                  ? "Current memory"
                  : "Latest historical version"}
              </span>

              <span
                className={`rounded-full px-2 py-1 text-xs font-semibold ${
                  currentClaim.status === "ACTIVE"
                    ? "bg-emerald-100 text-emerald-700"
                    : currentClaim.status === "SUPERSEDED"
                      ? "bg-amber-100 text-amber-700"
                      : "bg-slate-200 text-slate-700"
                }`}
              >
                {currentClaim.status}
              </span>
            </div>

            <p className="mt-3 wrap-break-word text-base font-semibold text-slate-900">
              {currentClaim.value}
            </p>
          </div>

          <dl className="mt-5 space-y-4 text-sm">
            <div>
              <dt className="flex items-center gap-2 font-medium text-slate-500">
                <Quote size={15} />
                Source utterance
              </dt>

              <dd className="mt-2 whitespace-pre-wrap wrap-break-word rounded-lg bg-slate-50 p-3 text-slate-700">
                {currentClaim.source_utterance
                  ? `“${currentClaim.source_utterance}”`
                  : "No source utterance recorded."}
              </dd>
            </div>

            <div>
              <dt className="flex items-center gap-2 font-medium text-slate-500">
                <CalendarDays size={15} />
                Created
              </dt>
              <dd className="mt-1 text-slate-700">
                {formatDate(currentClaim.created_at)}
              </dd>
            </div>

            <div>
              <dt className="flex items-center gap-2 font-medium text-slate-500">
                <Fingerprint size={15} />
                Memory key
              </dt>
              <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                {memoryKey}
              </dd>
            </div>

            <div>
              <dt className="font-medium text-slate-500">Claim ID</dt>
              <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                {currentClaim.claim_id}
              </dd>
            </div>
          </dl>
        </>
      )}

      {!loading && !error && !currentClaim && (
        <p className="mt-4 text-sm text-slate-500">
          No records found for this memory.
        </p>
      )}

      <div className="mt-6 border-t border-slate-200 pt-5">
        <div className="mb-4 flex items-center gap-2">
          <History size={18} className="text-blue-600" />

          <h3 className="font-semibold text-slate-900">Memory Evolution</h3>

          <span className="ml-auto rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
            {history.length} versions
          </span>
        </div>

        {!loading && !error && (
          <MemoryTimeline
            claims={history}
            highlightedClaimId={highlightedClaimId}
            navigationVersion={navigationVersion}
          />
        )}
      </div>
    </section>
  );
}
