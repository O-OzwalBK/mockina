import { ArrowRight, Clock3, Plus, Sparkles, Target } from "lucide-react";
import { Link } from "react-router-dom";
import PreparationCard from "../../components/preparation/PreparationCard";
import { usePreparations } from "../../hooks/usePreparations";
import "./DashboardPage.css";

export default function DashboardPage() {
  const { loading, error, data, retry } = usePreparations();
  const items = data ?? [];
  const sessions = items.reduce((sum, item) => sum + item.sessionCount, 0);
  const practised = items.filter((item) => item.sessionCount > 0).length;

  return (
    <div className="page-content dashboard-page">
      <section className="welcome-banner">
        <div className="welcome-copy">
          <span className="welcome-kicker">
            <Sparkles size={14} /> YOUR NEXT OPPORTUNITY STARTS HERE
          </span>
          <h1>
            Practice with purpose.
            <br />
            <em>Interview with confidence.</em>
          </h1>
          <p>Turn a little preparation into a big step forward in your career.</p>
          <Link className="btn btn-primary" to="/preparations/new">
            Create preparation <ArrowRight size={17} />
          </Link>
        </div>
        <div className="welcome-art">
          <div className="art-orbit orbit-one" />
          <div className="art-orbit orbit-two" />
          <div className="art-center">
            <Target size={42} />
          </div>
          <span className="float-chip chip-top">✦ Keep growing</span>
          <span className="float-chip chip-bottom">One step at a time</span>
        </div>
      </section>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-icon purple">
            <Target size={19} />
          </span>
          <span className="stat-label">Preparations</span>
          <strong>{loading ? "–" : items.length}</strong>
          <small>Keep your momentum going</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon green">
            <Sparkles size={19} />
          </span>
          <span className="stat-label">Sessions</span>
          <strong>{loading ? "–" : sessions}</strong>
          <small>Every session is progress</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon amber">
            <Clock3 size={19} />
          </span>
          <span className="stat-label">Practised preparations</span>
          <strong>{loading ? "–" : practised}</strong>
          <small>Time invested in yourself</small>
        </div>
      </div>

      <section className="section-block">
        <div className="section-header">
          <div>
            <h2>Continue preparing</h2>
            <p>Pick up where you left off.</p>
          </div>
          <Link to="/progress" className="text-link">
            View progress <ArrowRight size={15} />
          </Link>
        </div>

        {loading && (
          <div className="card" role="status">
            Loading your preparations…
          </div>
        )}

        {error && (
          <div className="card" role="alert">
            <p>{error.message}</p>
            {"retryable" in error && (error as { retryable: boolean }).retryable && (
              <button className="btn btn-secondary" onClick={retry}>
                Try again
              </button>
            )}
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <div className="card">
            <h3>Create your first preparation</h3>
            <p>A preparation is a job you want to practise for. Paste a job description to begin.</p>
            <Link className="btn btn-primary" to="/preparations/new">
              Create your first preparation
            </Link>
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <div className="prep-grid">
            {items.map((item) => (
              <PreparationCard key={item.id} item={item} />
            ))}
            <Link to="/preparations/new" className="new-prep-card">
              <span>
                <Plus size={23} />
              </span>
              <strong>Start a new preparation</strong>
              <small>Build a practice plan for your next role</small>
            </Link>
          </div>
        )}
      </section>

      <section className="tip-card">
        <span className="tip-star">
          <Sparkles size={20} />
        </span>
        <div>
          <strong>A little practice goes a long way</strong>
          <p>
            Try one focused interview session today. Review your report afterward to spot one thing to improve.
          </p>
        </div>
        <Link to="/preparations/new" aria-label="Start a new preparation">
          <ArrowRight size={18} />
        </Link>
      </section>
    </div>
  );
}
