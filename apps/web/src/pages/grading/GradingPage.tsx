import { CheckCircle2, FileText } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import "./GradingPage.css";

export default function GradingPage() {
  const { sessionId = "" } = useParams();

  return (
    <div className="page-content grading-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SESSION COMPLETE</p>
          <h1>Your interview is finished!</h1>
          <p>
            Your practice session has ended. You can now review your answers
            and available feedback in your report.
          </p>
        </div>
      </div>

      <section className="card grading-card">
        <div className="grading-spinner">
          <CheckCircle2 size={30} />
        </div>

        <h2>Interview grading complete</h2>
        <p>
          Your session is complete. Your report is ready to view.
        </p>

        <div className="grading-steps">
          <div className="grading-step done">
            <CheckCircle2 />
            <span>Interview session completed</span>
            <strong>Finished</strong>
          </div>

          <div className="grading-step done">
            <CheckCircle2 />
            <span>Preparing feedback</span>
            <strong>Finished</strong>
          </div>

          <div className="grading-step done">
            <FileText />
            <span>Report ready</span>
            <strong>Finished</strong>
          </div>
        </div>

        <Link
          to={`/reports/${sessionId}`}
          className="btn btn-primary"
        >
          View report page
        </Link>
      </section>
    </div>
  );
}
