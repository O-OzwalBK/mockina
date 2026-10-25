import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  abandonSession,
  completeSession,
  getNextTurn,
  getSession,
  submitAnswer,
} from "../../api";
import type { InterviewSession, Turn } from "../../api";
import { generateQuestionAudio, transcribeRecording } from "../../lib/speech";
import "./InterviewRoomPage.css";

type RoomState = "loading" | "asking" | "submitting" | "error" | "finished";

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

  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const microphoneStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const discardRecordingRef = useRef(false);

  const [cameraOn, setCameraOn] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speakingQuestion, setSpeakingQuestion] = useState(false);
  const [mediaError, setMediaError] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [recordingBlob, setRecordingBlob] = useState<Blob | null>(null);
  const [questionAudioUrl, setQuestionAudioUrl] = useState("");
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  const isBusy = roomState === "loading" || roomState === "submitting";

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = cameraStreamRef.current;
    }
  }, [cameraOn]);

  // Release camera and microphone resources when leaving the page.
  useEffect(() => {
    return () => {
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());

      if (recorderRef.current?.state === "recording") {
        recorderRef.current.stop();
      }
    };
  }, []);

  // Update the recording timer.
  useEffect(() => {
    if (!recording) return;

    const timer = window.setInterval(() => {
      setRecordingSeconds((seconds) => seconds + 1);
    }, 1000);

    return () => window.clearInterval(timer);
  }, [recording]);

  // Release old recording audio URLs.
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  // Release generated question audio URLs.
  useEffect(() => {
    return () => {
      if (questionAudioUrl) URL.revokeObjectURL(questionAudioUrl);
    };
  }, [questionAudioUrl]);

  const loadNextQuestion = useCallback(async () => {
    if (!sessionId) {
      setError("This interview link is missing its session ID.");
      setRoomState("error");
      return;
    }

    setRoomState("loading");
    setError("");
    setAnswer("");
    setTurn(null);

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
    const timer = window.setTimeout(() => {
      void loadNextQuestion();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loadNextQuestion]);

  async function toggleCamera() {
    setMediaError("");

    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;

      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }

      setCameraOn(false);
      return;
    }

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "Camera access is unavailable. Use HTTPS or localhost in a supported browser.",
        );
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });

      cameraStreamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraOn(true);
    } catch (cause) {
      setMediaError(
        cause instanceof Error ? cause.message : "Couldn't access your camera.",
      );
    }
  }

  async function startRecording() {
    setMediaError("");
    setRecordingSeconds(0);
    setRecordingBlob(null);
    setAudioUrl("");

    if (!navigator.mediaDevices?.getUserMedia) {
      setMediaError(
        "Microphone access is unavailable. Use HTTPS or localhost in a supported browser.",
      );
      return;
    }

    if (typeof MediaRecorder === "undefined") {
      setMediaError("Audio recording isn't supported by this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });

      microphoneStreamRef.current = stream;
      audioChunksRef.current = [];
      discardRecordingRef.current = false;

      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
      ].find((type) => MediaRecorder.isTypeSupported(type));

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        microphoneStreamRef.current
          ?.getTracks()
          .forEach((track) => track.stop());
        microphoneStreamRef.current = null;
        setRecording(false);

        if (discardRecordingRef.current) {
          audioChunksRef.current = [];
          discardRecordingRef.current = false;
          return;
        }

        const blob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });

        if (blob.size > 0) {
          setAudioUrl(URL.createObjectURL(blob));
          setRecordingBlob(blob);
        } else {
          setRecordingBlob(null);
          setMediaError("The recording was empty. Please try again.");
        }

        audioChunksRef.current = [];
      };

      recorder.start();
      setRecording(true);
    } catch (cause) {
      microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
      microphoneStreamRef.current = null;

      setMediaError(
        cause instanceof Error
          ? cause.message
          : "Couldn't access your microphone.",
      );
    }
  }

  function stopRecording() {
    const recorder = recorderRef.current;

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
      microphoneStreamRef.current = null;
      setRecording(false);
    }
  }

  function deleteRecording() {
    if (recorderRef.current?.state === "recording") {
      discardRecordingRef.current = true;
      recorderRef.current.stop();
    }

    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
    microphoneStreamRef.current = null;
    audioChunksRef.current = [];

    setRecording(false);
    setRecordingSeconds(0);
    setRecordingBlob(null);
    setAudioUrl("");
    setMediaError("");
  }

  async function startSpeechToText() {
    if (!recordingBlob || transcribing) return;

    setMediaError("");
    setTranscribing(true);

    try {
      const transcript = await transcribeRecording(recordingBlob);

      setAnswer((current) =>
        current.trim() ? `${current.trimEnd()} ${transcript}` : transcript,
      );
    } catch (cause) {
      setMediaError(
        cause instanceof Error
          ? cause.message
          : "Couldn't transcribe your recording.",
      );
    } finally {
      setTranscribing(false);
    }
  }

  async function readQuestionAloud() {
    if (!turn?.question.text || speakingQuestion) return;

    setMediaError("");
    setSpeakingQuestion(true);

    try {
      const audioBlob = await generateQuestionAudio(turn.question.text);
      const newUrl = URL.createObjectURL(audioBlob);

      setQuestionAudioUrl((previousUrl) => {
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        return newUrl;
      });
    } catch (cause) {
      setMediaError(
        cause instanceof Error
          ? cause.message
          : "Couldn't generate spoken audio for the question.",
      );
    } finally {
      setSpeakingQuestion(false);
    }
  }

  function formatTime(totalSeconds: number) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  async function handleSubmit() {
    if (!sessionId || !turn || !answer.trim() || roomState === "submitting") {
      return;
    }

    if (recording) stopRecording();

    setRoomState("submitting");
    setError("");

    try {
      await submitAnswer(sessionId, turn.question.id, {
        transcript: answer.trim(),
        duration: 0,
        words: [],
      });

      setSubmittedCount((count) => count + 1);
      setRecordingBlob(null);
      setAudioUrl("");
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
    if (recording) stopRecording();

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

    if (recording) stopRecording();

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
  console.log({
    isBusy,
    turn,
    transcribing,
  });
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

        <section className="interview-media-card">
          <h2>Camera and microphone</h2>

          <div className="interview-media-grid">
            <div className="interview-camera-panel">
              <video
                ref={videoRef}
                className="interview-camera-preview"
                autoPlay
                muted
                playsInline
                aria-label="Your live camera preview"
              />

              {!cameraOn && (
                <div className="interview-camera-placeholder">
                  <span aria-hidden="true">▣</span>
                  <p>Camera is off</p>
                </div>
              )}
            </div>

            <div className="interview-audio-panel">
              <div>
                <strong>Camera</strong>
                <p>
                  {cameraOn
                    ? "Your camera is on."
                    : "Your video is not being shared."}
                </p>

                <button
                  type="button"
                  onClick={() => void toggleCamera()}
                  disabled={isBusy}
                >
                  {cameraOn ? "Turn camera off" : "Turn camera on"}
                </button>
              </div>

              <div>
                <strong>Microphone recording</strong>
                <p>
                  {recording
                    ? `Recording audio · ${formatTime(recordingSeconds)}`
                    : "Record a spoken answer on this device."}
                </p>
                {!recording ? (
                  <button
                    type="button"
                    onClick={() => void startRecording()}
                    disabled={isBusy || !turn || transcribing}
                  >
                    Start recording
                  </button>
                ) : (
                  <button type="button" onClick={stopRecording}>
                    Stop recording
                  </button>
                )}
              </div>
            </div>
          </div>

          {mediaError && (
            <p className="interview-error" role="alert">
              {mediaError}
            </p>
          )}

          {audioUrl && (
            <div className="interview-recording-playback">
              <strong>Your latest recording</strong>

              <audio controls src={audioUrl}>
                Your browser does not support audio playback.
              </audio>

              <button type="button" onClick={deleteRecording}>
                Delete recording
              </button>

              <p>
                Your recording is available for playback in this room. It is
                processed locally for transcription and is not uploaded to a
                transcription API.
              </p>
            </div>
          )}

          <div className="interview-speech-controls">
            <strong>On-device speech-to-text</strong>

            <p>
              Record your answer, stop the recording, and transcribe it into the
              answer field using the Whisper model on your device.
            </p>

            <button
              type="button"
              onClick={() => void startSpeechToText()}
              disabled={!recordingBlob || recording || transcribing || isBusy}
            >
              {transcribing
                ? "Transcribing on this device…"
                : "Transcribe recording"}
            </button>

            {transcribing && (
              <span aria-live="polite">
                Loading or running the speech model. The first run may take
                longer.
              </span>
            )}
          </div>
        </section>

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
            <>
              <div className="interview-question-meta">
                <span>
                  Skill: {turn.question.skill_id.replaceAll("_", " ")}
                </span>
                <span>Difficulty {turn.question.difficulty}/5</span>
              </div>

              <div className="interview-speech-controls">
                <strong>Listen to the question</strong>

                <p>
                  Generate spoken audio on your device using the text-to-speech
                  model.
                </p>

                <button
                  type="button"
                  onClick={() => void readQuestionAloud()}
                  disabled={speakingQuestion || isBusy}
                >
                  {speakingQuestion
                    ? "Generating question audio…"
                    : "Read question aloud"}
                </button>

                {questionAudioUrl && (
                  <audio
                    controls
                    src={questionAudioUrl}
                    aria-label="Spoken interview question"
                  >
                    Your browser does not support audio playback.
                  </audio>
                )}
              </div>
            </>
          )}
        </section>

        {roomState !== "loading" && roomState !== "finished" && (
          <section className="interview-answer-card">
            <label htmlFor="interview-answer">Your written answer</label>

            <p>
              Write your response below or transcribe a recording to fill this
              field. Review your answer before submitting.
            </p>

            <textarea
              id="interview-answer"
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              placeholder="Start writing or speaking your answer here…"
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
