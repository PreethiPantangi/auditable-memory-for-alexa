import { useEffect, useState } from "react";

import Sidebar from "./components/layout/Sidebar";
import ChatPanel from "./components/chat/ChatPanel";
import MemoryLedger from "./components/memory/MemoryLedger";
import DemoLogin from "./components/auth/DemoLogin";

import { checkDemoSession, loginDemo } from "./services/demoAuthApi";

export default function App() {
  const [refreshVersion, setRefreshVersion] = useState(0);

  const [selectedMemoryKey, setSelectedMemoryKey] = useState<string | null>(
    null,
  );

  const [highlightedClaimId, setHighlightedClaimId] = useState<string | null>(
    null,
  );

  const [navigationVersion, setNavigationVersion] = useState(0);

  const [authStatus, setAuthStatus] = useState<
    "checking" | "authenticated" | "unauthenticated"
  >("checking");

  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      try {
        const session = await checkDemoSession();

        if (cancelled) return;

        if (session.authenticated && session.username) {
          setUsername(session.username);
          setAuthStatus("authenticated");
        } else {
          setUsername(null);
          setAuthStatus("unauthenticated");
        }
      } catch {
        if (!cancelled) {
          setUsername(null);
          setAuthStatus("unauthenticated");
        }
      }
    }

    void restoreSession();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogin(inputUsername: string, password: string) {
    const session = await loginDemo(inputUsername, password);

    if (!session.authenticated || !session.username) {
      throw new Error("Login failed.");
    }

    setUsername(session.username);
    setSelectedMemoryKey(null);
    setHighlightedClaimId(null);
    setRefreshVersion(0);
    setNavigationVersion(0);
    setAuthStatus("authenticated");
  }

  function handleLogout() {
    setUsername(null);
    setAuthStatus("unauthenticated");
    setSelectedMemoryKey(null);
    setHighlightedClaimId(null);
    setRefreshVersion(0);
    setNavigationVersion(0);
  }

  function handleMemoryChanged() {
    setRefreshVersion((version) => version + 1);
  }

  function handleViewMemory(memoryKey: string, claimId?: string | null) {
    setSelectedMemoryKey(memoryKey);
    setHighlightedClaimId(claimId ?? null);

    setNavigationVersion((previous) => previous + 1);
  }

  function handleSelectMemory(memoryKey: string) {
    setSelectedMemoryKey(memoryKey);
    setHighlightedClaimId(null);
  }

  if (authStatus === "checking") {
    return (
      <div
        className="flex min-h-screen items-center justify-center text-sm text-slate-500"
        role="status"
      >
        Checking demo access...
      </div>
    );
  }

  if (authStatus === "unauthenticated" || !username) {
    return <DemoLogin onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[230px_minmax(0,1fr)]">
        <Sidebar onLogout={handleLogout} />

        <main className="grid min-w-0 grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(350px,1fr)]">
          <ChatPanel
            key={username}
            userId={username}
            onMemoryChanged={handleMemoryChanged}
            onViewMemory={handleViewMemory}
          />

          <MemoryLedger
            key={username}
            userId={username}
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
