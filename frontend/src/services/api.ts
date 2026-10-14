import type { ChatResponse } from "../types/chat";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function sendMessage(
  userId: string,
  conversationId: string,
  message: string,
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      conversation_id: conversationId,
      message,
      request_id: crypto.randomUUID(),
    }),
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const result: unknown = await response.json();

  if (
    typeof result !== "object" ||
    result === null ||
    !("message" in result) ||
    typeof result.message !== "string" ||
    !("actions" in result) ||
    !Array.isArray(result.actions)
  ) {
    throw new Error("Unexpected chat API response.");
  }

  return result as ChatResponse;
}
