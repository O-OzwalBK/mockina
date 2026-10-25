import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createIdentity, getCapabilities, getStoredIdentity, storeIdentity } from "../api";
import { CapabilitiesContext } from "./capabilities";

async function boot() {
  if (!getStoredIdentity()) storeIdentity(await createIdentity());
  return getCapabilities();
}

/** Gate that provides identity and capabilities to everything below it. */
export default function Boot({ children }: { children: ReactNode }) {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["boot"],
    queryFn: boot,
    staleTime: Infinity,
    retry: false,
  });

  if (isPending) return <p role="status">Starting Mockina…</p>;
  if (error || !data) {
    return (
      <div role="alert">
        <p>{error?.message ?? "The server could not be reached."}</p>
        <button type="button" onClick={() => void refetch()}>
          Retry
        </button>
      </div>
    );
  }
  return <CapabilitiesContext value={data}>{children}</CapabilitiesContext>;
}
