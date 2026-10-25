import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Download,
  Lightbulb,
  Target,
  MessageSquareText,
  CircleAlert,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { getSession } from "../../api";
import type { InterviewSession } from "../../api";
import "./ReportPage.css";

export default function ReportPage() {
  const { reportId = "" } = useParams();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      setLoading(true);
      setError("");

      try {
        const result = await getSession(reportId);

        if (!cancelled) {
          setSession(result);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not load the interview report.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    if (reportId) {
      void loadReport();
    } else {
      setError("The report ID is missing.");
      setLoading(false);
    }

    return () => {
      cancelled = true;
    };
  }, [reportId]);

  if (loading) {
    return (
      <div className="page-content report-page">
        <p className="eyebrow">YOUR SESSION REVIEW</p>
        <h1>Loading report</h1>
        <p>Retrieving your interview results...</p>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="page-content report-page">
        <Link to="/" className="back-link">
          <ArrowLeft size={16} /> Dashboard
        </Link>
        <section className="card">
          <CircleAlert size={24} />
          <h1>Report unavailable</h1>
          <p>{error || "We couldn't find this interview session."}</p>
          <button
            className="btn btn-secondary"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
        </section>
      </div>
    );
  }

  const turns = session.turns.filter((turn) => turn.answer !== null);
  const gradedTurns = turns.filter(
    (turn) => turn.status === "graded" && turn.evaluation !== null,
  );

  const metrics = [
    { key: "clarity", label: "Clarity" },
    { key: "relevance", label: "Relevance" },
    { key: "correctness", label: "Correctness" },
    { key: "depth", label: "Depth" },
  ] as const;

  const scores = gradedTurns.flatMap((turn) =>
    metrics.map((metric) => turn.evaluation![metric.key].score),
  );

  const averageScore = scores.length
    ? scores.reduce((total, score) => total + score, 0) / scores.length
    : null;

  const allScores = gradedTurns.flatMap((turn) =>
    metrics.map((metric) => ({
      label: metric.label,
      score: turn.evaluation![metric.key].score,
      feedback: turn.evaluation![metric.key].feedback,
    })),
  );

  return (
    <div className="page-content report-page">
      <Link to="/" className="back-link">
        <ArrowLeft size={16} /> Dashboard
      </Link>

      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR SESSION REVIEW</p>
          <h1>Interview report</h1>
          <p>Review your answers and feedback from this practice session.</p>
        </div>

        <button
          className="btn btn-secondary"
          onClick={() => window.print()}
        >
          <Download size={16} /> Print report
        </button>
      </div>

      <section className="card">
        <p className="eyebrow">SESSION SUMMARY</p>
        <div className="grid grid-2">
          <div>
            <h2>{turns.length}</h2>
            <p className="muted">Answers submitted</p>
          </div>
          <div>
            <h2>
              {averageScore === null
                ? "N/A"
                : `${averageScore.toFixed(1)}/10`}
            </h2>
            <p className="muted">Average demonstration score</p>
          </div>
        </div>
        <p className="muted">
          Session status: {session.status}
        </p>
      </section>

      <div className="report-notice">
        <Lightbulb size={19} />
        <div>
          <strong>About these results</strong>
          <p>
            The current development mock uses demonstration scores based
            partly on answer length. They are not verified AI assessments
            of factual correctness or interview performance.
          </p>
        </div>
      </div>

      <section className="card">
        <span className="report-icon">
          <Target />
        </span>
        <h2>Evaluation feedback</h2>

        {gradedTurns.length === 0 ? (
          <p className="muted">
            No graded answers are available for this session yet.
          </p>
        ) : (
          gradedTurns.map((turn, index) => (
            <div key={turn.question.id} className="report-answer">
              <h3>
                Question {index + 1}: {turn.question.text}
              </h3>

              <p>
                <strong>Your answer</strong>
              </p>
              <p>{turn.answer?.transcript || "No transcript available."}</p>

              <div className="grid grid-2 report-grid">
                {metrics.map((metric) => {
                  const result = turn.evaluation![metric.key];

                  return (
                    <section className="card" key={metric.key}>
                      <h3>{metric.label}</h3>
                      <p>
                        <strong>{result.score}/10</strong>
                      </p>
                      <p className="muted">{result.feedback}</p>
                    </section>
                  );
                })}
              </div>

              <div>
                <span className="report-icon mint">
                  <MessageSquareText />
                </span>
                <h3>Summary</h3>
                <p>{turn.evaluation!.summary}</p>
              </div>
            </div>
          ))
        )}
      </section>

      {gradedTurns.length > 0 && (
        <section className="card">
          <h2>Feedback overview</h2>
          {allScores.map((item, index) => (
            <div key={`${item.label}-${index}`}>
              <p>
                <strong>{item.label}: {item.score}/10</strong>
              </p>
              <p className="muted">{item.feedback}</p>
            </div>
          ))}
        </section>
      )}

      <section className="card report-next">
        <h2>Plan your next practice</h2>
        <p>
          Use the feedback above to decide what you want to improve in your
          next interview.
        </p>
        <Link to="/" className="btn btn-primary">
          Back to home
        </Link>
        <small>Report reference: {reportId}</small>
      </section>
    </div>
  );
}
