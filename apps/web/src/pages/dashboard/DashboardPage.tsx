import { ArrowRight, Clock3, Plus, Sparkles, Target } from "lucide-react";
import { Link } from "react-router-dom";
import "./DashboardPage.css";

const preparations = [
  {
    id: "frontend",
    title: "Frontend Developer",
    company: "Practice interview",
    level: "Intermediate",
    questions: 10,
    progress: 60,
    color: "violet",
  },
  {
    id: "qa",
    title: "QA Automation Engineer",
    company: "Career preparation",
    level: "Beginner friendly",
    questions: 8,
    progress: 25,
    color: "blue",
  },
];

export default function DashboardPage() {
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
          <p>
            Turn a little preparation into a big step forward in your career.
          </p>
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
          <strong>02</strong>
          <small>Keep your momentum going</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon green">
            <Sparkles size={19} />
          </span>
          <span className="stat-label">Sessions completed</span>
          <strong>04</strong>
          <small>Every session is progress</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon amber">
            <Clock3 size={19} />
          </span>
          <span className="stat-label">Practice time</span>
          <strong>1.5h</strong>
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
        <div className="prep-grid">
          {preparations.map((item) => (
            <article className="prep-card card" key={item.id}>
              <div className={`prep-symbol ${item.color}`}>
                <Target size={22} />
              </div>
              <span className="pill">{item.level}</span>
              <h3>{item.title}</h3>
              <p>{item.company}</p>
              <div className="prep-meta">
                <span>{item.questions} questions</span>
                <span>{item.progress}% complete</span>
              </div>
              <div className="progress-track">
                <span style={{ width: `${item.progress}%` }} />
              </div>
              <Link
                className="btn btn-secondary prep-action"
                to={`/preparations/${item.id}`}
              >
                Continue <ArrowRight size={15} />
              </Link>
            </article>
          ))}
          <Link to="/preparations/new" className="new-prep-card">
            <span>
              <Plus size={23} />
            </span>
            <strong>Start a new preparation</strong>
            <small>Build a practice plan for your next role</small>
          </Link>
        </div>
      </section>
      <section className="tip-card">
        <span className="tip-star">
          <Sparkles size={20} />
        </span>
        <div>
          <strong>A little practice goes a long way</strong>
          <p>
            Try one focused interview session today. Review your report
            afterward to spot one thing to improve.
          </p>
        </div>
        <Link to="/guides" aria-label="Explore interview guides">
          <ArrowRight size={18} />
        </Link>
      </section>
    </div>
  );
}
