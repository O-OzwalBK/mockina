import { useParams } from "react-router-dom";

/** Interview room. Real question flow comes once the session routes exist on the server. */
export default function InterviewRoomPage() {
  const { sessionId } = useParams();
  return (
    <section>
      <h1>Interview room</h1>
      <p>Session: {sessionId}</p>
    </section>
  );
}
