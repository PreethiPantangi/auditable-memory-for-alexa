
import type {
  MemoryListResponse,
  MemoryHistoryResponse,
} from "../types/memory";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function getMemories(
  userId: string
): Promise<MemoryListResponse> {
  const response = await fetch(
    `${API_BASE_URL}/memories?user_id=${encodeURIComponent(userId)}`
  );

  if (!response.ok) {
    throw new Error("Failed to load memories");
  }

  return response.json();
}

export async function getMemoryHistory(
  userId: string,
  memoryKey: string
): Promise<MemoryHistoryResponse> {
  const response = await fetch(
    `${API_BASE_URL}/memories/${encodeURIComponent(memoryKey)}/history?user_id=${encodeURIComponent(userId)}`
  );

  if (!response.ok) {
    throw new Error("Failed to load memory history");
  }

  return response.json();
}
