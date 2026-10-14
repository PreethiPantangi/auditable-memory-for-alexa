import type {
  InsightListResponse,
  InsightEvidenceResponse,
  InsightDecisionResponse,
  DeriveInsightsResponse,
} from "../types/insight";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(
  /\/$/,
  "",
);

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail?.message ??
        (typeof error?.detail === "string"
          ? error.detail
          : `Request failed (${response.status})`),
    );
  }

  return (await response.json()) as T;
}

export function getInsights(userId: string): Promise<InsightListResponse> {
  return apiRequest(`/insights?user_id=${encodeURIComponent(userId)}`);
}

export function getInsightEvidence(
  userId: string,
  insightId: number,
): Promise<InsightEvidenceResponse> {
  return apiRequest(
    `/insights/${insightId}/evidence?user_id=${encodeURIComponent(userId)}`,
  );
}

export function deriveInsights(
  userId: string,
): Promise<DeriveInsightsResponse> {
  return apiRequest(`/insights/derive?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function decideInsight(
  userId: string,
  insightId: number,
  decision: "confirm" | "reject",
): Promise<InsightDecisionResponse> {
  return apiRequest(
    `/insights/${insightId}/${decision}?user_id=${encodeURIComponent(userId)}`,
    {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    },
  );
}
