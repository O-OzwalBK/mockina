import { ArrowRight, Target } from "lucide-react";
import { Link } from "react-router-dom";
import type { PreparationSummary } from "../../services/preparationsApi";

const formatDate = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(iso));

/** One preparation on the Dashboard. */
export default function PreparationCard({ item }: { item: PreparationSummary }) {
  const practised = item.sessionCount > 0;
  return (
    <article className="prep-card card">
      <span className="prep-symbol violet">
        <Target size={22} />
      </span>
      <span className="pill">{practised ? "Practised" : "New"}</span>
      <h3>{item.title}</h3>
      <p>Created {formatDate(item.createdAt)}</p>
      <div className="prep-meta">
        <span>
          {item.sessionCount} {item.sessionCount === 1 ? "session" : "sessions"}
        </span>
        <span>
          {item.lastPractisedAt ? `Last practised ${formatDate(item.lastPractisedAt)}` : "Not practised yet"}
        </span>
      </div>
      <Link className="btn btn-secondary prep-action" to={`/preparations/${item.id}`}>
        Open <ArrowRight size={15} />
      </Link>
    </article>
  );
}
