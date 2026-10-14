import type {
  MemoryListResponse,
  MemoryHistoryResponse,
} from "../types/memory";

import type { MemoryExplanation } from "../types/memory";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function getMemories(userId: string): Promise<MemoryListResponse> {
  const response = await fetch(
    `${API_BASE_URL}/memories?user_id=${encodeURIComponent(userId)}`,
    {
      credentials: "include",
    },
  );

  if (!response.ok) {
    throw new Error("Failed to load memories");
  }

  return response.json();
}

export async function getMemoryHistory(
  userId: string,
  memoryKey: string,
): Promise<MemoryHistoryResponse> {
  const response = await fetch(
    `${API_BASE_URL}/memories/${encodeURIComponent(memoryKey)}/history?user_id=${encodeURIComponent(userId)}`,
    {
      credentials: "include",
    },
  );

  if (!response.ok) {
    throw new Error("Failed to load memory history");
  }

  return response.json();
}

export async function getMemoryExplanation(
  userId: string,
  claimId: string,
  signal?: AbortSignal,
): Promise<MemoryExplanation> {
  const response = await fetch(
    `${API_BASE_URL}/memories/${encodeURIComponent(claimId)}/explain?user_id=${encodeURIComponent(userId)}`,
    {
      credentials: "include",
      signal,
    },
  );

  if (!response.ok) {
    throw new Error("Failed to load memory explanation");
  }

  return response.json() as Promise<MemoryExplanation>;
}
