import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

import MemoryList from "./MemoryList";
import MemoryDetail from "./MemoryDetail";

import { getMemories } from "../../services/memoryApi";
import type { MemoryClaim } from "../../types/memory";

interface Props {
  userId: string;
  refreshVersion: number;
  selectedMemoryKey: string | null;
  highlightedClaimId: string | null;
  onSelectMemory: (memoryKey: string) => void;
  navigationVersion: number;
}

export default function MemoryLedger({
  userId,
  refreshVersion,
  selectedMemoryKey,
  highlightedClaimId,
  onSelectMemory,
  navigationVersion,
}: Props) {
  const [memories, setMemories] = useState<MemoryClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manualRefresh, setManualRefresh] = useState(0);

  const memoryDetailsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selectedMemoryKey || navigationVersion === 0) return;

    const frame = requestAnimationFrame(() => {
      memoryDetailsRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
        inline: "nearest",
      });
    });

    return () => cancelAnimationFrame(frame);
  }, [selectedMemoryKey, navigationVersion]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMemories() {
      setLoading(true);

      try {
        const result = await getMemories(userId);

        if (!cancelled) {
          setMemories(result.memories);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError("Unable to load memories.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchMemories();

    return () => {
      cancelled = true;
    };
  }, [userId, refreshVersion, manualRefresh]);

  function handleRefresh() {
    setManualRefresh((previous) => previous + 1);
  }

  // F3: Determine the selected memory using the key
  // received from App.tsx.
  const selectedMemory =
    memories.find((memory) => memory.memory_key === selectedMemoryKey) ?? null;

  function handleSelect(memory: MemoryClaim) {
    onSelectMemory(memory.memory_key);
  }

  return (
    <div
      id="memory-ledger-scroll"
      className="flex min-w-0 flex-col gap-4 overflow-y-auto xl:h-[calc(100vh-32px)] xl:overscroll-contain"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-slate-600">Memory Ledger</h2>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={loading}
          aria-label="Refresh memories"
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-50"
        >
          <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {loading && <p className="text-sm text-slate-500">Loading memories...</p>}

      <MemoryList
        memories={memories}
        selectedKey={selectedMemoryKey}
        onSelect={handleSelect}
      />

      <div ref={memoryDetailsRef} id="memory-details" className="scroll-mt-4">
        <MemoryDetail
          key={`${userId}-${selectedMemoryKey}-${refreshVersion}-${manualRefresh}`}
          userId={userId}
          memory={selectedMemory}
          selectedMemoryKey={selectedMemoryKey}
          highlightedClaimId={highlightedClaimId}
          navigationVersion={navigationVersion}
        />
      </div>
    </div>
  );
}
