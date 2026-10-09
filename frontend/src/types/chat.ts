export interface ChatAction {
  intent: string;
  category: string | null;
  result: {
    success: boolean;
    data?: unknown;
    error?: {
      code: string;
      message: string;
    };
  };
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions?: ChatAction[];
}

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
}
