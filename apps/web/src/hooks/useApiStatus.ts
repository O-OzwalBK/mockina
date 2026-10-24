import { useEffect, useState } from "react";
import { getHealth } from "../services/api";

export type ApiStatus = "checking" | "online" | "offline";

/** Checks once whether the API answers /health. */
export function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => setStatus("online"))
      .catch(() => {
        if (!controller.signal.aborted) setStatus("offline");
      });
    return () => controller.abort();
  }, []);

  return status;
}
