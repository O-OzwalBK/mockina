import { createContext, useContext } from "react";
import type { Capabilities } from "../api";

export const CapabilitiesContext = createContext<Capabilities | null>(null);

/** Reads instance capabilities; only valid below the Boot gate. */
export function useCapabilities(): Capabilities {
  const value = useContext(CapabilitiesContext);
  if (!value) throw new Error("useCapabilities must be used inside Boot.");
  return value;
}
