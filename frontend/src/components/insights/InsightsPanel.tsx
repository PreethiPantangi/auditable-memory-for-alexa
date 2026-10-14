import { useCallback, useEffect, useState } from "react";

import {
  decideInsight,
  deriveInsights,
  getInsightEvidence,
  getInsights,
} from "../../services/insightsApi";

import type { Insight, InsightEvent } from "../../types/insight";

import "./InsightsPanel.css";

interface InsightsPanelProps {
  userId: string;
  onMemoryChanged?: () => void | Promise<void>;
}

export default function InsightsPanel({
  userId,
  onMemoryChanged,
}: InsightsPanelProps) {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [evidence, setEvidence] = useState<Record<number, InsightEvent[]>>({});
  const [evidenceLoadingId, setEvidenceLoadingId] = useState<number | null>(
    null,
  );
  const [busyId, setBusyId] = useState<number | null>(null);
  const [deriving, setDeriving] = useState(false);
  const [deriveMessage, setDeriveMessage] = useState<string | null>(null);

  const loadInsights = useCallback(async () => {
    const result = await getInsights(userId);
    setInsights(result.insights);
  }, [userId]);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      setInsights([]);
      setEvidence({});
      setExpandedId(null);

      try {
        const result = await getInsights(userId);
        if (active) setInsights(result.insights);
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Unable to load insights",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [userId]);

  async function toggleEvidence(insightId: number) {
    if (expandedId === insightId) {
      setExpandedId(null);
      return;
    }

    setExpandedId(insightId);

    if (evidence[insightId]) return;

    setEvidenceLoadingId(insightId);
    setError(null);

    try {
      const result = await getInsightEvidence(userId, insightId);
      setEvidence((previous) => ({
        ...previous,
        [insightId]: result.events,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load evidence");
    } finally {
      setEvidenceLoadingId(null);
    }
  }

  async function handleDecision(
    insightId: number,
    decision: "confirm" | "reject",
  ) {
    setBusyId(insightId);
    setError(null);

    try {
      await decideInsight(userId, insightId, decision);
      await loadInsights();

      if (decision === "confirm") {
        await onMemoryChanged?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update insight");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDerive() {
    setDeriving(true);
    setError(null);
    setDeriveMessage(null);

    try {
      const result = await deriveInsights(userId);

      await loadInsights();

      if (result.created_count > 0) {
        setDeriveMessage(
          `Found ${result.created_count} new insight${
            result.created_count === 1 ? "" : "s"
          }. Review the pending candidates below.`,
        );
      } else {
        setDeriveMessage(
          "No new insights found. Record at least three positive cooking experiences for the same dish and adjustment.",
        );
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to derive insights",
      );
    } finally {
      setDeriving(false);
    }
  }

  return (
    <section className="insights-panel">
      <header className="insights-header">
        <div>
          <h2>Memory Insights</h2>
          <p>Review patterns discovered from your experiences.</p>
        </div>

        <button
          type="button"
          onClick={() => void handleDerive()}
          disabled={deriving || loading || busyId !== null}
        >
          {deriving ? "Analyzing..." : "Find insights"}
        </button>
      </header>

      {error && (
        <div role="alert" className="insights-error">
          {error}
        </div>
      )}

      {deriveMessage && (
        <div
          role="status"
          className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800"
        >
          {deriveMessage}
        </div>
      )}

      {loading ? (
        <p>Loading insights...</p>
      ) : insights.length === 0 ? (
        <p className="insights-empty">
          No insights yet. Record cooking experiences and select Find insights.
        </p>
      ) : (
        <div className="insights-list">
          {insights.map((insight) => {
            const isPending = insight.status === "PENDING_CONFIRMATION";
            const isExpanded = expandedId === insight.insight_id;
            const isBusy = busyId === insight.insight_id;

            return (
              <article key={insight.insight_id} className="insight-card">
                <div className="insight-card-heading">
                  <h3>{insight.subject}</h3>
                  <span
                    className={`insight-status ${insight.status.toLowerCase()}`}
                  >
                    {insight.status.replaceAll("_", " ")}
                  </span>
                </div>

                <p>{insight.statement}</p>

                <p className="insight-metadata">
                  {insight.evidence_count} evidence records
                  {insight.confirmed_claim_id !== null &&
                    ` · Memory #${insight.confirmed_claim_id}`}
                </p>

                <button
                  type="button"
                  className="insight-evidence-toggle"
                  onClick={() => void toggleEvidence(insight.insight_id)}
                  aria-expanded={isExpanded}
                >
                  {isExpanded ? "Hide evidence" : "View evidence"}
                </button>

                {isExpanded && (
                  <div className="insight-evidence">
                    {evidenceLoadingId === insight.insight_id ? (
                      <p>Loading evidence...</p>
                    ) : evidence[insight.insight_id] ? (
                      <ul>
                        {evidence[insight.insight_id].map((event) => (
                          <li key={event.id}>
                            <p>
                              <strong>Event #{event.id}</strong>
                              {" · "}
                              {event.outcome ?? "Unknown outcome"}
                            </p>
                            <p>{event.source_utterance}</p>
                            <time dateTime={event.occurred_at}>
                              {new Date(event.occurred_at).toLocaleString()}
                            </time>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>Evidence could not be loaded.</p>
                    )}
                  </div>
                )}

                {isPending && (
                  <div className="insight-actions">
                    <button
                      type="button"
                      disabled={isBusy || busyId !== null || deriving}
                      onClick={() =>
                        void handleDecision(insight.insight_id, "confirm")
                      }
                    >
                      {isBusy ? "Saving..." : "Confirm"}
                    </button>

                    <button
                      type="button"
                      className="insight-reject"
                      disabled={isBusy || busyId !== null || deriving}
                      onClick={() =>
                        void handleDecision(insight.insight_id, "reject")
                      }
                    >
                      Reject
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
