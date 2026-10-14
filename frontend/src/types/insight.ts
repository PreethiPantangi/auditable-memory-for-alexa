export type InsightStatus = "PENDING_CONFIRMATION" | "CONFIRMED" | "REJECTED";

export interface Insight {
  insight_id: number;
  domain: string;
  insight_type: string;
  subject: string;
  adjustment: string;
  statement: string;
  status: InsightStatus;
  confirmed_claim_id: number | null;
  evidence_count: number;
  created_at: string;
  decided_at: string | null;
}

export interface InsightListResponse {
  insights: Insight[];
  count: number;
}

export interface InsightEvent {
  id: number;
  subject: string;
  attributes: Record<string, unknown>;
  outcome: string | null;
  source_utterance: string;
  occurred_at: string;
}

export interface InsightEvidenceResponse {
  insight_id: number;
  statement: string;
  status: InsightStatus;
  events: InsightEvent[];
  count: number;
}

export interface InsightDecisionResponse {
  insight_id: number;
  status?: InsightStatus;
  claim_id?: number;
  already_confirmed?: boolean;
  already_rejected?: boolean;
}

export interface DeriveInsightsResponse {
  created: Insight[];
  created_count: number;
}
