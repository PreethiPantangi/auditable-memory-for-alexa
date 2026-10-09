import { useCallback, useState } from "react";
import type { ReactNode } from "react";

import { MemoryNavigationContext } from "./MemoryNavigationContext";
import type { MemoryNavigationTarget } from "../types/memory";

export default function MemoryNavigationProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [target, setTarget] = useState<MemoryNavigationTarget | null>(null);

  const navigateToMemory = useCallback((nextTarget: MemoryNavigationTarget) => {
    setTarget(nextTarget);
  }, []);

  const clearNavigation = useCallback(() => {
    setTarget(null);
  }, []);

  return (
    <MemoryNavigationContext.Provider
      value={{
        target,
        navigateToMemory,
        clearNavigation,
      }}
    >
      {children}
    </MemoryNavigationContext.Provider>
  );
}
