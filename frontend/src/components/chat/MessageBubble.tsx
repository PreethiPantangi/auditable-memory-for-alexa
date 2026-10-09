
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BrainCircuit } from "lucide-react";

import type { ChatMessage } from "../../types/chat";
import MemoryActionCard from "./MemoryActionCard";

interface Props {
  message: ChatMessage;

  // F3: Navigate to the selected memory and claim
  onViewMemory: (
    memoryKey: string,
    claimId?: string | null
  ) => void;
}

export default function MessageBubble({
  message,
  onViewMemory,
}: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex gap-3 ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {!isUser && (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600">
          <BrainCircuit size={19} />
        </div>
      )}

      <div
        className={`min-w-0 max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-blue-100 text-slate-900"
            : "bg-slate-100 text-slate-800"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">
            {message.content}
          </p>
        ) : (
          <div className="space-y-2 wrap-break-word">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => (
                  <p>{children}</p>
                ),

                strong: ({ children }) => (
                  <strong className="font-semibold text-slate-900">
                    {children}
                  </strong>
                ),

                ul: ({ children }) => (
                  <ul className="list-disc space-y-1 pl-5">
                    {children}
                  </ul>
                ),

                ol: ({ children }) => (
                  <ol className="list-decimal space-y-1 pl-5">
                    {children}
                  </ol>
                ),

                code: ({ children }) => (
                  <code className="rounded bg-slate-200 px-1 py-0.5 font-mono text-xs break-all">
                    {children}
                  </code>
                ),

                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-blue-300 pl-3 italic text-slate-600">
                    {children}
                  </blockquote>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {message.actions?.map((action, index) => (
          <MemoryActionCard
            key={`${message.id}-${index}`}
            action={action}
            onViewMemory={onViewMemory}
          />
        ))}
      </div>
    </div>
  );
}
