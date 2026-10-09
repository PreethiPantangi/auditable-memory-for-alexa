import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

interface Props {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatComposer({ onSend, disabled = false }: Props) {
  const [input, setInput] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const message = input.trim();
    if (!message || disabled) return;

    onSend(message);
    setInput("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-3 rounded-2xl border border-slate-200 bg-white p-3"
    >
      <textarea
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Tell me something to remember..."
        rows={2}
        aria-label="Chat message"
        className="min-w-0 flex-1 resize-none bg-transparent p-2 text-sm outline-none placeholder:text-slate-400 disabled:opacity-50"
      />

      <button
        type="submit"
        disabled={disabled || !input.trim()}
        aria-label="Send message"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Send size={18} />
      </button>
    </form>
  );
}
