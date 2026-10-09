import { createContext } from "react";
import type { MemoryNavigationTarget } from "../types/memory";

export interface MemoryNavigationContextValue {
  target: MemoryNavigationTarget | null;
  navigateToMemory: (target: MemoryNavigationTarget) => void;
  clearNavigation: () => void;
}

export const MemoryNavigationContext =
  createContext<MemoryNavigationContextValue | null>(null);
