import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  abandonSession,
  completeSession,
  getNextTurn,
  getSession,
  submitAnswer,
} from "../../api";
import type { InterviewSession, Turn } from "../../api";
import "./InterviewRoomPage.css";

type RoomState = "loading" | "asking" | "submitting" | "error" | "finished";

/** Provides a typed-answer interview room backed by the session API. */
export default function InterviewRoomPage() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [answer, setAnswer] = useState("");
  const [roomState, setRoomState] = useState<RoomState>("loading");
  const [error, setError] = useState("");
  const [submittedCount, setSubmittedCount] = useState(0);
  const [confirmEnd, setConfirmEnd] = useState(false);

  const loadNextQuestion = useCallback(async () => {
    if (!sessionId) {
      setError("This interview link is missing its session ID.");
      setRoomState("error");
      return;
    }
    setRoomState("loading");
    setError("");
    setAnswer("");
    try {
      const currentSession = await getSession(sessionId);
      setSession(currentSession);
      if (currentSession.status !== "in_progress") {
        navigate(`/grading/${sessionId}`, { replace: true });
        return;
      }
      const nextTurn = await getNextTurn(sessionId);
      setTurn(nextTurn);
      setRoomState("asking");
    } catch (cause) {
      const message =
        cause instanceof Error
          ? cause.message
          : "Couldn't load the next question.";
      if (/session_finished|no more questions|already ended/i.test(message)) {
        setTurn(null);
        setRoomState("finished");
        return;
      }
      setError(message);
      setRoomState("error");
    }
  }, [navigate, sessionId]);

  useEffect(() => {
    void loadNextQuestion();
  }, [loadNextQuestion]);

  async function handleSubmit() {
    if (!sessionId || !turn || !answer.trim() || roomState === "submitting")
      return;
    setRoomState("submitting");
    setError("");
    try {
      await submitAnswer(sessionId, turn.question.id, {
        transcript: answer.trim(),
        duration: 0,
        words: [],
      });
      setSubmittedCount((count) => count + 1);
      await loadNextQuestion();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Couldn't submit your answer. Please try again.",
      );
      setRoomState("error");
    }
  }

  async function handleLeave() {
    if (!sessionId) {
      navigate("/");
      return;
    }
    try {
      await abandonSession(sessionId);
    } catch {
      // Leave the room even if the server cannot update the session.
    }
    navigate(session ? `/preparations/${session.preparation_id}` : "/");
  }

  async function handleEnd() {
    if (!sessionId) return;
    setRoomState("submitting");
    setError("");
    try {
      await completeSession(sessionId);
      navigate(`/grading/${sessionId}`);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Couldn't end this interview.",
      );
      setRoomState("error");
    }
  }

  const isBusy = roomState === "loading" || roomState === "submitting";

  return (
    <div className="interview-room">
      <header className="interview-topbar">
        <div className="interview-brand">
          <span className="interview-brand-mark">M</span> Mockina
        </div>
        <div className="interview-live">
          <span /> Practice interview
        </div>
        <button
          className="interview-leave"
          type="button"
          onClick={() => void handleLeave()}
          disabled={isBusy}
        >
          Leave interview
        </button>
      </header>

      <main className="interview-content">
        <div className="interview-eyebrow">YOUR INTERVIEW ROOM</div>
        <h1>Take a moment. Think clearly.</h1>
        <p className="interview-intro">
          Answer as if you were speaking to a real interviewer. You can take
          your time.
        </p>

        <div className="interview-progress-row">
          <span className="interview-status-dot" />
          <span>
            {roomState === "loading"
              ? "Preparing question"
              : roomState === "submitting"
                ? "Saving your answer"
                : "Your turn to answer"}
          </span>
          <span className="interview-answer-count">
            {submittedCount} {submittedCount === 1 ? "answer" : "answers"}{" "}
            submitted
          </span>
        </div>

        <section className="interview-question-card" aria-live="polite">
          <div className="interview-card-label">
            <span>✦</span> INTERVIEW QUESTION
          </div>
          {roomState === "loading" ? (
            <div className="interview-loading">
              <span className="interview-spinner" />
              Preparing your next question…
            </div>
          ) : roomState === "finished" ? (
            <h2>That was the last question.</h2>
          ) : (
            <h2>
              {turn?.question.text ?? "Your next question will appear here."}
            </h2>
          )}
          {turn && roomState !== "loading" && (
            <div className="interview-question-meta">
              <span>Skill: {turn.question.skill_id.replaceAll("_", " ")}</span>
              <span>Difficulty {turn.question.difficulty}/5</span>
            </div>
          )}
        </section>

        {roomState !== "loading" && roomState !== "finished" && (
          <section className="interview-answer-card">
            <label htmlFor="interview-answer">Your answer</label>
            <p>
              Write your response below. Aim to explain your reasoning and give
              a specific example where possible.
            </p>
            <textarea
              id="interview-answer"
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              placeholder="Start writing your answer here…"
              rows={7}
              maxLength={20000}
              disabled={isBusy || !turn}
            />
            <div className="interview-answer-footer">
              <span>{answer.length.toLocaleString()} / 20,000 characters</span>
              <button
                type="button"
                className="interview-submit"
                onClick={() => void handleSubmit()}
                disabled={!answer.trim() || isBusy || !turn}
              >
                {roomState === "submitting" ? "Saving…" : "Submit answer →"}
              </button>
            </div>
          </section>
        )}

        {roomState === "error" && (
          <div className="interview-error" role="alert">
            <strong>Something went wrong</strong>
            <p>{error || "Please try again."}</p>
            <button type="button" onClick={() => void loadNextQuestion()}>
              Retry loading question
            </button>
          </div>
        )}

        {roomState === "finished" && (
          <button
            type="button"
            className="interview-submit"
            onClick={() => void handleEnd()}
          >
            Finish interview →
          </button>
        )}

        {submittedCount > 0 && roomState !== "submitting" && (
          <div className="interview-end-row">
            <span>Ready to stop? Your submitted answers will be kept.</span>
            <button
              type="button"
              className="interview-end-button"
              onClick={() => setConfirmEnd(true)}
            >
              End interview
            </button>
          </div>
        )}
      </main>

      {confirmEnd && (
        <div className="interview-dialog-backdrop" role="presentation">
          <section
            className="interview-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="end-dialog-title"
          >
            <h2 id="end-dialog-title">End this interview?</h2>
            <p>
              Your submitted answers will be saved. You won't be able to answer
              more questions in this session.
            </p>
            <div className="interview-dialog-actions">
              <button
                type="button"
                className="interview-secondary"
                onClick={() => setConfirmEnd(false)}
              >
                Keep practising
              </button>
              <button
                type="button"
                className="interview-submit"
                onClick={() => void handleEnd()}
                disabled={isBusy}
              >
                End interview
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
