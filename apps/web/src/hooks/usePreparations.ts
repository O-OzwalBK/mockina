import { useEffect, useState } from "react";
import { getPreparations, type PreparationSummary } from "../services/preparationsApi";

type Result = { attempt: number; data?: PreparationSummary[]; error?: Error } | null;

/** Loads preparations and exposes loading, error and a retry function. */
export function usePreparations() {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result>(null);

  useEffect(() => {
    const controller = new AbortController();
    getPreparations(controller.signal)
      .then((data) => setResult({ attempt, data }))
      .catch((error: Error) => {
        if (!controller.signal.aborted) setResult({ attempt, error });
      });
    return () => controller.abort();
  }, [attempt]);

  const loading = result === null || result.attempt !== attempt;
  return {
    loading,
    error: loading ? undefined : result?.error,
    data: loading ? undefined : result?.data,
    retry: () => setAttempt((n) => n + 1),
  };
}
