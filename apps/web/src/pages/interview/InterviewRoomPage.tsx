import { useState } from "react";
import { Mic, MicOff, PhoneOff, ShieldCheck } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import "./InterviewRoomPage.css";
export default function InterviewRoomPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [micOn, setMicOn] = useState(false);
  const [started, setStarted] = useState(false);
  return (
    <div className="page-content interview-page">
      <div className="interview-top">
        <div>
          <p className="eyebrow">PRACTICE SESSION</p>
          <h1>Interview room</h1>
        </div>
        <span className="session-private">
          <ShieldCheck size={15} /> Private practice
        </span>
      </div>
      <section className="interview-stage">
        <div className="stage-orb">
          <div className="stage-avatar">M</div>
          <span
            className={`audio-ring ${micOn && started ? "speaking" : ""}`}
          />
        </div>
        <span className="stage-status">
          {started ? "Session ready" : "Your interview space"}
        </span>
        <h2>
          {started ? "Take a breath. You’ve got this." : "Ready when you are."}
        </h2>
        <p>
          {started
            ? "Speak clearly and answer at your own pace."
            : "Check your microphone, then begin your practice session."}
        </p>
        <div className="interview-controls">
          <button
            className={`control-button ${micOn ? "control-active" : ""}`}
            onClick={() => setMicOn((v) => !v)}
            aria-label={micOn ? "Turn microphone off" : "Turn microphone on"}
          >
            {micOn ? <Mic size={20} /> : <MicOff size={20} />}
            <span>{micOn ? "Mic on" : "Mic off"}</span>
          </button>
          {!started ? (
            <button
              className="btn btn-primary start-session"
              onClick={() => setStarted(true)}
            >
              Begin interview
            </button>
          ) : (
            <button
              className="btn btn-primary start-session"
              onClick={() => navigate(`/grading/${sessionId}`)}
            >
              <PhoneOff size={17} /> End interview
            </button>
          )}
        </div>
        <div className="room-privacy">
          <ShieldCheck size={15} /> Your interview feedback and scores will be
          available after you finish.
        </div>
      </section>
    </div>
  );
}
