
import { useState } from "react";

import Sidebar from "./components/layout/Sidebar";
import ChatPanel from "./components/chat/ChatPanel";
import MemoryLedger from "./components/memory/MemoryLedger";

import { DEMO_USER_ID } from "./lib/demo";

export default function App() {
  const [refreshVersion, setRefreshVersion] = useState(0);

  // F3: Select a logical memory from a chat action
  const [selectedMemoryKey, setSelectedMemoryKey] =
    useState<string | null>(null);

  // F3: Highlight a specific version in the timeline
  const [highlightedClaimId, setHighlightedClaimId] =
    useState<string | null>(null);

  const [navigationVersion, setNavigationVersion] =
  useState(0);

  function handleMemoryChanged() {
    setRefreshVersion((version) => version + 1);
  }

  // Called when the user clicks "View memory history"
  // on a chat action card.
  function handleViewMemory(
  memoryKey: string,
  claimId?: string | null
) {
  setSelectedMemoryKey(memoryKey);
  setHighlightedClaimId(claimId ?? null);

  setNavigationVersion((previous) => previous + 1);
}

  // Called when a different memory is selected manually
  // from the Memory Ledger.
  function handleSelectMemory(memoryKey: string) {
    setSelectedMemoryKey(memoryKey);
    setHighlightedClaimId(null);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[230px_minmax(0,1fr)]">
        <Sidebar />

        <main className="grid min-w-0 grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(350px,1fr)]">
          <ChatPanel
            onMemoryChanged={handleMemoryChanged}
            onViewMemory={handleViewMemory}
          />

          <MemoryLedger
            userId={DEMO_USER_ID}
            refreshVersion={refreshVersion}
            selectedMemoryKey={selectedMemoryKey}
            highlightedClaimId={highlightedClaimId}
            onSelectMemory={handleSelectMemory}
            navigationVersion={navigationVersion}
          />
        </main>
      </div>
    </div>
  );
}
