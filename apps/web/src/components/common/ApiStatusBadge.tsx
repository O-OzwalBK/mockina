import { useApiStatus } from "../../hooks/useApiStatus";

const LABELS = {
  checking: "Checking server…",
  online: "Server online",
  offline: "Server offline",
} as const;

/** Small text status for the Settings page or the app header. */
export default function ApiStatusBadge() {
  const status = useApiStatus();
  return (
    <span role="status" aria-live="polite">
      {LABELS[status]}
    </span>
  );
}
