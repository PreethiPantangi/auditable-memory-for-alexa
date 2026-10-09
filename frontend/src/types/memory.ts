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

export interface MemoryHistory {
  memory_key: string;
  claims: MemoryClaim[];
}

export interface MemoryNavigationTarget {
  memoryKey: string;
  claimId?: string | null;
}

export interface MemoryClaim {
  claim_id: string;
  user_id: string;
  category: string;
  memory_key: string;
  value: string;
  status: "ACTIVE" | "SUPERSEDED" | "FORGOTTEN";
  source_type: string;
  source_utterance: string | null;
  created_at: string;
  superseded_by_claim_id: string | null;
}

export interface MemoryListResponse {
  memories: MemoryClaim[];
}

export interface MemoryHistoryResponse {
  history: MemoryClaim[];
}

export interface NavigationTarget {
  memoryKey: string;
  claimId?: string | null;
  requestId: number;
}
