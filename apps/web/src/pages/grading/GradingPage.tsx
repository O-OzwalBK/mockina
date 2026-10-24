import { CheckCircle2, Clock3, FileText, LoaderCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import "./GradingPage.css";
export default function GradingPage() {
  const { sessionId } = useParams();
  return (
    <div className="page-content grading-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SESSION COMPLETE</p>
          <h1>Preparing your report</h1>
          <p>
            Your practice session is complete. Your feedback will appear here
            when analysis finishes.
          </p>
        </div>
      </div>
      <section className="card grading-card">
        <div className="grading-spinner">
          <LoaderCircle size={30} />
        </div>
        <h2>Reviewing your interview</h2>
        <p>
          Mockina is organizing your session feedback. You can leave this page
          and return later.
        </p>
        <div className="grading-steps">
          <div className="grading-step done">
            <CheckCircle2 />
            <span>Interview session completed</span>
            <strong>Done</strong>
          </div>
          <div className="grading-step active">
            <Clock3 />
            <span>Preparing feedback</span>
            <strong>In progress</strong>
          </div>
          <div className="grading-step">
            <FileText />
            <span>Report ready</span>
            <strong>Pending</strong>
          </div>
        </div>
        <Link to={`/reports/${sessionId}`} className="btn btn-secondary">
          View report page
        </Link>
      </section>
    </div>
  );
}
