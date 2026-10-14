import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle } from "lucide-react";

import type { MemoryExplanation } from "../../types/memory";
import { getMemoryExplanation } from "../../services/memoryApi";

interface Props {
  userId: string;
  claimId: string;
}

function formatDate(value: string) {
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "Unknown date"
    : date.toLocaleDateString();
}

export default function MemoryEvidence({ userId, claimId }: Props) {
  const [explanation, setExplanation] = useState<MemoryExplanation | null>(
    null,
  );

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const result = await getMemoryExplanation(
          userId,
          claimId,
          controller.signal,
        );

        if (!controller.signal.aborted) {
          setExplanation(result);
          setError(null);
        }
      } catch {
        if (!controller.signal.aborted) {
          setError("Unable to load supporting evidence.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => controller.abort();
  }, [userId, claimId]);

  if (loading) {
    return (
      <p role="status" className="text-sm text-slate-500">
        Loading supporting evidence...
      </p>
    );
  }

  if (error || !explanation) {
    return (
      <p role="alert" className="text-sm text-red-600">
        {error ?? "Explanation unavailable."}
      </p>
    );
  }

  if (explanation.source_type !== "INFERRED_CONFIRMED") {
    return (
      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-500">
          Original user statement
        </p>
        <p className="whitespace-pre-wrap text-sm text-slate-800">
          {explanation.source_utterance ?? "No original statement recorded."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {explanation.insight && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-blue-800">
            <CheckCircle2 size={16} />
            Confirmed insight #{explanation.insight.id}
          </div>

          <p className="mt-2 text-sm text-slate-800">
            {explanation.insight.statement}
          </p>
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold text-slate-800">
          Supporting cooking observations
        </h4>

        <p className="mt-1 text-xs text-slate-500">
          {explanation.evidence_count ?? 0} observations
        </p>
      </div>

      {explanation.evidence?.map((event) => (
        <div
          key={event.event_id}
          className="rounded-lg border border-slate-200 bg-white p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-slate-500">
              Event #{event.event_id} · {formatDate(event.occurred_at)}
            </span>

            <span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700">
              {event.outcome}
            </span>
          </div>

          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">
            {event.source_utterance}
          </p>
        </div>
      ))}

      {!explanation.provenance_complete && (
        <div
          role="alert"
          className="flex items-center gap-2 text-sm text-amber-700"
        >
          <AlertCircle size={16} />
          Complete supporting evidence is unavailable.
        </div>
      )}
    </div>
  );
}
