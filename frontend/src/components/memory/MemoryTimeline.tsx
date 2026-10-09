import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Clock3,
  Archive,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Quote,
  Fingerprint,
} from "lucide-react";

import type { MemoryClaim } from "../../types/memory";

interface Props {
  claims: MemoryClaim[];
  highlightedClaimId?: string | null;
  navigationVersion?: number;
}

function formatDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown date";
  }

  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function shortId(id: string) {
  return id.length > 12 ? `${id.slice(0, 8)}...` : id;
}

const statusConfig = {
  ACTIVE: {
    label: "Active",
    icon: CheckCircle2,
    badge: "bg-emerald-100 text-emerald-700",
    dot: "bg-emerald-500",
    border: "border-emerald-200",
  },
  SUPERSEDED: {
    label: "Superseded",
    icon: Clock3,
    badge: "bg-amber-100 text-amber-700",
    dot: "bg-amber-500",
    border: "border-amber-200",
  },
  FORGOTTEN: {
    label: "Forgotten",
    icon: Archive,
    badge: "bg-slate-200 text-slate-700",
    dot: "bg-slate-400",
    border: "border-slate-200",
  },
};

export default function MemoryTimeline({
  claims,
  highlightedClaimId,
  navigationVersion,
}: Props) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  const highlightedRef = useRef<HTMLLIElement>(null);

  const sortedClaims = [...claims].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  // A correction relationship must be based on
  // superseded_by_claim_id, not simply timestamps.
  const claimMap = new Map(
    sortedClaims.map((claim) => [claim.claim_id, claim]),
  );

  const predecessors = new Map<string, MemoryClaim[]>();

  for (const claim of sortedClaims) {
    if (!claim.superseded_by_claim_id) continue;

    const existing = predecessors.get(claim.superseded_by_claim_id) ?? [];

    predecessors.set(claim.superseded_by_claim_id, [...existing, claim]);
  }

  useEffect(() => {
    if (!highlightedClaimId) return;

    let frame1 = 0;
    let frame2 = 0;

    frame1 = requestAnimationFrame(() => {
      frame2 = requestAnimationFrame(() => {
        const target = highlightedRef.current;
        const container = document.getElementById("memory-ledger-scroll");

        if (!target || !container) return;

        // Calculate the target's position relative
        // to the scrollable ledger container.
        // const targetRect = target.getBoundingClientRect();
        // const containerRect = container.getBoundingClientRect();

        // const relativeTop =
        //   targetRect.top -
        //   containerRect.top +
        //   container.scrollTop;

        // const desiredScrollTop =
        //   relativeTop -
        //   container.clientHeight / 2 +
        //   targetRect.height / 2;

        // container.scrollTo({
        //   top: Math.max(0, desiredScrollTop),
        //   behavior: "smooth",
        // });
      });
    });

    return () => {
      cancelAnimationFrame(frame1);
      cancelAnimationFrame(frame2);
    };
  }, [highlightedClaimId, navigationVersion, claims]);

  function toggleExpanded(claimId: string) {
    setExpandedIds((previous) => {
      const next = new Set(previous);

      if (next.has(claimId)) {
        next.delete(claimId);
      } else {
        next.add(claimId);
      }

      return next;
    });
  }

  if (sortedClaims.length === 0) {
    return (
      <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
        No version history is available.
      </p>
    );
  }

  if (new Set(sortedClaims.map((claim) => claim.memory_key)).size > 1) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Cannot display timeline: mismatched memory keys.
      </p>
    );
  }

  return (
    <ol className="space-y-0" aria-label="Memory version timeline">
      {sortedClaims.map((claim, index) => {
        const config = statusConfig[claim.status] ?? statusConfig.SUPERSEDED;

        const StatusIcon = config.icon;

        const isExpanded =
          expandedIds.has(claim.claim_id) ||
          highlightedClaimId === claim.claim_id;

        const isHighlighted = highlightedClaimId === claim.claim_id;

        const successor = claim.superseded_by_claim_id
          ? claimMap.get(claim.superseded_by_claim_id)
          : undefined;

        const previousVersions = predecessors.get(claim.claim_id) ?? [];

        return (
          <li
            key={claim.claim_id}
            ref={isHighlighted ? highlightedRef : undefined}
            className="relative flex gap-3 scroll-mt-6"
          >
            <div className="flex w-5 shrink-0 flex-col items-center">
              <div
                className={`mt-5 h-3 w-3 shrink-0 rounded-full ring-4 ring-white ${config.dot}`}
                aria-hidden="true"
              />

              {index < sortedClaims.length - 1 && (
                <div
                  className="min-h-6 w-0.5 flex-1 bg-slate-200"
                  aria-hidden="true"
                />
              )}
            </div>

            <article
              className={`mb-4 min-w-0 flex-1 rounded-xl border bg-white p-4 shadow-sm ${
                isHighlighted
                  ? "border-blue-400 ring-2 ring-blue-200"
                  : config.border
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${config.badge}`}
                >
                  <StatusIcon size={13} />
                  {config.label}
                </span>

                <time
                  className="text-xs text-slate-500"
                  dateTime={claim.created_at}
                >
                  {formatDate(claim.created_at)}
                </time>
              </div>

              <p className="mt-3 wrap-break-word text-sm font-semibold text-slate-900">
                {claim.value}
              </p>

              {isHighlighted && (
                <p className="mt-2 text-xs font-medium text-blue-700">
                  Selected from chat
                </p>
              )}

              {successor && (
                <div className="mt-3 flex flex-wrap items-center gap-1 text-xs text-slate-500">
                  <ArrowRight size={13} />
                  Superseded by
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedIds((previous) => {
                        const next = new Set(previous);
                        next.add(successor.claim_id);
                        return next;
                      })
                    }
                    className="font-mono text-blue-600 underline"
                  >
                    {shortId(successor.claim_id)}
                  </button>
                </div>
              )}

              {previousVersions.length > 0 && (
                <div className="mt-2 text-xs text-slate-500">
                  Replaces:{" "}
                  {previousVersions.map((previous, i) => (
                    <span key={previous.claim_id}>
                      {i > 0 ? ", " : ""}
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedIds((current) => {
                            const next = new Set(current);
                            next.add(previous.claim_id);
                            return next;
                          })
                        }
                        className="font-mono text-blue-600 underline"
                      >
                        {shortId(previous.claim_id)}
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {claim.status === "FORGOTTEN" && (
                <p className="mt-3 rounded-lg bg-slate-50 p-2 text-xs text-slate-600">
                  Inactive memory retained in the audit history.
                </p>
              )}

              {claim.superseded_by_claim_id && !successor && (
                <p className="mt-2 text-xs text-amber-700">
                  Linked replacement is not present in this history response.
                </p>
              )}

              <button
                type="button"
                onClick={() => toggleExpanded(claim.claim_id)}
                aria-expanded={isExpanded}
                aria-controls={`evidence-${claim.claim_id}`}
                className="mt-4 flex w-full items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                <span>
                  {isExpanded ? "Hide source evidence" : "View source evidence"}
                </span>

                {isExpanded ? (
                  <ChevronUp size={16} />
                ) : (
                  <ChevronDown size={16} />
                )}
              </button>

              {isExpanded && (
                <div
                  id={`evidence-${claim.claim_id}`}
                  className="mt-3 space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-3"
                >
                  <div>
                    <p className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <Quote size={14} />
                      Original source utterance
                    </p>

                    <blockquote className="mt-2 whitespace-pre-wrap wrap-break-word text-sm italic text-slate-800">
                      {claim.source_utterance
                        ? `“${claim.source_utterance}”`
                        : "No source utterance recorded."}
                    </blockquote>
                  </div>

                  <div>
                    <p className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <Fingerprint size={14} />
                      Claim ID
                    </p>

                    <p className="mt-1 break-all font-mono text-xs text-slate-700">
                      {claim.claim_id}
                    </p>
                  </div>

                  <dl className="space-y-2 text-xs">
                    <div>
                      <dt className="text-slate-500">Source type</dt>
                      <dd className="text-slate-800">{claim.source_type}</dd>
                    </div>

                    <div>
                      <dt className="text-slate-500">Category</dt>
                      <dd className="text-slate-800">{claim.category}</dd>
                    </div>

                    <div>
                      <dt className="text-slate-500">Memory key</dt>
                      <dd className="break-all font-mono text-slate-800">
                        {claim.memory_key}
                      </dd>
                    </div>

                    <div>
                      <dt className="text-slate-500">Created at</dt>
                      <dd className="text-slate-800">
                        {formatDate(claim.created_at)}
                      </dd>
                    </div>
                  </dl>
                </div>
              )}
            </article>
          </li>
        );
      })}
    </ol>
  );
}
