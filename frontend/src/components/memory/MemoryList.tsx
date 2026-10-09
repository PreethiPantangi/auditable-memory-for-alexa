
import { useMemo, useState } from "react";
import { Search, Database } from "lucide-react";
import type { MemoryClaim } from "../../types/memory";

interface Props {
  memories: MemoryClaim[];
  selectedKey: string | null;
  onSelect: (memory: MemoryClaim) => void;
}

type Filter = "ACTIVE" | "FORGOTTEN" | "ALL";

export default function MemoryList({
  memories,
  selectedKey,
  onSelect,
}: Props) {
  const [filter, setFilter] = useState<Filter>("ACTIVE");
  const [search, setSearch] = useState("");

  const filteredMemories = useMemo(() => {
    return memories.filter((memory) => {
      const matchesStatus =
        filter === "ALL" || memory.status === filter;

      const term = search.toLowerCase();

      const matchesSearch =
        memory.value.toLowerCase().includes(term) ||
        memory.category.toLowerCase().includes(term) ||
        (memory.source_utterance ?? "").toLowerCase().includes(term);

      return matchesStatus && matchesSearch;
    });
  }, [memories, filter, search]);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-xl font-bold">Your Memories</h2>
      <p className="mt-1 text-sm text-slate-500">
        What I remember, and where it came from.
      </p>

      <div className="relative mt-5">
        <Search
          size={17}
          className="absolute left-3 top-3 text-slate-400"
        />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search memories..."
          aria-label="Search memories"
          className="w-full rounded-xl border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500"
        />
      </div>

      <div className="mt-4 flex gap-2">
        {(["ACTIVE", "FORGOTTEN", "ALL"] as const).map(
          (status) => (
            <button
              key={status}
              onClick={() => setFilter(status)}
              aria-pressed={filter === status}
              className={`rounded-lg px-3 py-2 text-xs font-medium ${
                filter === status
                  ? "bg-blue-100 text-blue-700"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {status === "ALL"
                ? "All"
                : status === "ACTIVE"
                  ? "Active"
                  : "Forgotten"}
            </button>
          )
        )}
      </div>

      <div className="mt-5 space-y-3">
        {filteredMemories.length === 0 && (
          <div className="py-8 text-center text-slate-400">
            <Database size={30} className="mx-auto mb-3" />
            <p className="text-sm">No matching memories.</p>
          </div>
        )}

        {filteredMemories.map((memory) => (
          <button
            key={memory.memory_key}
            onClick={() => onSelect(memory)}
            className={`w-full rounded-xl border p-4 text-left transition ${
              selectedKey === memory.memory_key
                ? "border-blue-400 bg-blue-50"
                : "border-slate-200 hover:bg-slate-50"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm font-semibold capitalize">
                {memory.category.replaceAll("_", " ")}
              </span>

              <span
                className={`rounded-full px-2 py-1 text-xs ${
                  memory.status === "ACTIVE"
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {memory.status}
              </span>
            </div>

            <p className="mt-2 text-sm text-slate-700">
              {memory.value}
            </p>

            <p className="mt-2 text-xs text-slate-400">
              {new Date(memory.created_at).toLocaleDateString()}
            </p>
          </button>
        ))}
      </div>
    </section>
  );
}
