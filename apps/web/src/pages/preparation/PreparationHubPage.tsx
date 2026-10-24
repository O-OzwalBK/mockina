import {
  ArrowLeft,
  ArrowRight,
  ClipboardList,
  Mic,
  PencilLine,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import "./PreparationHubPage.css";
export default function PreparationHubPage() {
  const { preparationId } = useParams();
  const title =
    preparationId === "qa"
      ? "QA Automation Engineer"
      : preparationId === "new"
        ? "Create a preparation"
        : "Frontend Developer";
  return (
    <div className="page-content hub-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={16} /> Back to dashboard
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PREPARATION WORKSPACE</p>
          <h1>{title}</h1>
          <p>Review your setup, get ready, and start when you feel prepared.</p>
        </div>
        <span className="pill">Draft workspace</span>
      </div>
      <div className="hub-layout">
        <section className="card hub-main">
          <span className="hub-hero-icon">
            <ClipboardList size={27} />
          </span>
          <h2>You're in the right place to prepare</h2>
          <p>
            Check your interview focus and make sure your setup is ready before
            starting a session.
          </p>
          <div className="hub-check-row">
            <span>1</span>
            <div>
              <strong>Review your interview focus</strong>
              <p>Role, topics, and experience level</p>
            </div>
            <PencilLine size={18} />
          </div>
          <div className="hub-check-row">
            <span>2</span>
            <div>
              <strong>Check your microphone</strong>
              <p>Make sure your browser can access audio</p>
            </div>
            <Mic size={18} />
          </div>
          <Link
            className="btn btn-primary hub-start"
            to={`/interview/${preparationId}-session`}
          >
            Start practice interview <ArrowRight size={17} />
          </Link>
          <small className="hub-disclaimer">
            The interview room should not display scores or feedback while the
            session is in progress.
          </small>
        </section>
        <aside className="card hub-side">
          <h3>Before you begin</h3>
          <ul>
            <li>Find a quiet place</li>
            <li>Allow microphone access when prompted</li>
            <li>Speak naturally and take your time</li>
            <li>Review your report after the session</li>
          </ul>
        </aside>
      </div>
    </div>
  );
}
