import { useQuery } from "@tanstack/react-query";
import { getPreparations } from "../api";

/** Loads preparations and exposes loading, error and a retry function. */
export function usePreparations() {
  const query = useQuery({ queryKey: ["preparations"], queryFn: getPreparations });
  return {
    loading: query.isPending,
    error: query.error ?? undefined,
    data: query.data?.items.map((row) => ({
      id: row.id,
      title: row.job_title,
      createdAt: row.created_at,
      sessionCount: row.session_count,
      lastPractisedAt: row.last_session_at,
    })),
    retry: () => void query.refetch(),
  };
}
