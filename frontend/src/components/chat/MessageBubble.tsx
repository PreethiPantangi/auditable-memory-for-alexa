import ReactMarkdown from "react-markdown";
import { Bot, User } from "lucide-react";

import MemoryActionCard from "./MemoryActionCard";

import type { ChatAction } from "../../types/chat";

interface Message {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  actions?: ChatAction[];
}

interface MessageBubbleProps {
  message: Message;
  onViewMemory: (memoryKey: string, claimId?: string | null) => void;
}

export default function MessageBubble({
  message,
  onViewMemory,
}: MessageBubbleProps) {
  const isAssistant = message.role === "assistant";

  return (
    <div
      className={`flex w-full gap-3 ${
        isAssistant ? "justify-start" : "justify-end"
      }`}
    >
      {isAssistant && (
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600">
          <Bot size={21} aria-hidden="true" />
        </div>
      )}

      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
          isAssistant
            ? "bg-slate-100 text-slate-900"
            : "bg-blue-100 text-slate-900"
        }`}
      >
        {/* Chat message */}
        <div className="chat-markdown text-sm leading-6">
          <ReactMarkdown>{message.content ?? ""}</ReactMarkdown>
        </div>

        {/* Real API action cards */}
        {isAssistant &&
          message.actions?.map((action, index) => (
            <MemoryActionCard
              key={`${message.id}-action-${index}`}
              action={action}
              onViewMemory={onViewMemory}
            />
          ))}
      </div>

      {!isAssistant && (
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
          <User size={20} aria-hidden="true" />
        </div>
      )}
    </div>
  );
}
