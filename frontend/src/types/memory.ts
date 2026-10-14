export type MemoryStatus = "ACTIVE" | "SUPERSEDED" | "FORGOTTEN";

export interface MemoryClaim {
  claim_id: string;
  user_id: string;
  category: string;
  memory_key: string;
  value: string;
  source_type: string;
  source_utterance: string | null;
  status: MemoryStatus;
  created_at: string;
  superseded_by_claim_id: string | null;
}

export interface MemoryListResponse {
  memories: MemoryClaim[];
}

export interface MemoryHistoryResponse {
  history: MemoryClaim[];
}

export interface MemoryNavigationTarget {
  memoryKey: string;
  claimId?: string | null;
}

export interface NavigationTarget {
  memoryKey: string;
  claimId?: string | null;
  requestId: number;
}

export interface InsightProvenance {
  id: number;
  domain: string;
  insight_type: string;
  subject: string;
  adjustment: string;
  statement: string;
  status: string;
  decided_at: string | null;
}

export interface CookingEvidence {
  event_id: number;
  user_id: string;
  domain: string;
  event_type: string;
  subject: string;
  attributes: Record<string, unknown>;
  outcome: string;
  source_type: string;
  source_utterance: string;
  occurred_at: string;
}

export interface MemoryExplanation extends MemoryClaim {
  insight?: InsightProvenance | null;
  evidence?: CookingEvidence[];
  evidence_count?: number;
  provenance_complete?: boolean;
}
