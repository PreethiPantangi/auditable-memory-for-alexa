import { useEffect, useRef, useState } from "react";
import { BrainCircuit, AlertCircle } from "lucide-react";

import ChatComposer from "./ChatComposer";
import MessageBubble from "./MessageBubble";

import { sendMessage } from "../../services/api";
import type { ChatMessage } from "../../types/chat";

const welcomeMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Hi! I can remember your preferences, explain where memories came from, and show how they changed. What would you like me to remember?",
};

type ChatPanelProps = {
  userId: string;
  onMemoryChanged: () => void;
  onViewMemory: (memoryKey: string, claimId?: string | null) => void;
};

export default function ChatPanel({
  userId,
  onMemoryChanged,
  onViewMemory,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inFlightRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages, loading]);

  async function handleSend(content: string) {
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    setLoading(true);
    setError(null);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
    };

    setMessages((previous) => [...previous, userMessage]);

    try {
      const result = await sendMessage(userId, content);

      // Existing F2 behavior:
      // Refresh the ledger only after successful mutations.
      const memoryChanged = result.actions.some(
        (action) =>
          action.result?.success === true &&
          ["remember", "correct_memory", "forget"].includes(
            action.intent.toLowerCase(),
          ),
      );

      if (memoryChanged) {
        onMemoryChanged();
      }

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.message,
        actions: result.actions,
      };

      setMessages((previous) => [...previous, assistantMessage]);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Something went wrong.";

      setError(
        `${message} The result is unknown. Check your memories before retrying.`,
      );
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }

  return (
    <section className="flex min-h-150 min-w-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm xl:h-[calc(100vh-32px)]">
      <header className="border-b border-slate-100 p-6">
        <h1 className="text-2xl font-bold">Chat with Alexa+</h1>

        <p className="mt-2 text-sm text-slate-500">
          I remember what matters, explain my answers, and learn from our
          conversations.
        </p>

        <span className="mt-2 inline-block rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700">
          Demo identity: {userId}
        </span>
      </header>

      <div
        aria-live="polite"
        className="flex flex-1 flex-col gap-5 overflow-y-auto p-5"
      >
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onViewMemory={onViewMemory}
          />
        ))}

        {loading && (
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <BrainCircuit size={20} className="animate-pulse text-blue-600" />
            Checking memory...
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-100 p-4">
        {error && (
          <div
            role="alert"
            className="mb-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700"
          >
            <AlertCircle size={18} className="shrink-0" />
            {error}
          </div>
        )}

        <ChatComposer onSend={handleSend} disabled={loading} />
      </div>
    </section>
  );
}
