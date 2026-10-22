/* Generated from docs/schemas. Do not edit by hand. */

/**
 * When the session ended. Present only when the status is completed or abandoned.
 */
export type EndedAt = string | null;
/**
 * Globally unique identifier of the session, generated when it is created.
 */
export type Id = string;
/**
 * The id of the preparation (job description and resume) this session practices.
 */
export type PreparationId = string;
/**
 * When the session started, as a timezone-aware UTC time.
 */
export type StartedAt = string;
/**
 * Where the session is in its life cycle.
 */
export type SessionStatus = 'in_progress' | 'completed' | 'abandoned';
/**
 * Total length of the answer in seconds.
 */
export type Duration = number;
/**
 * Full text of the answer. Empty if the user stayed silent.
 */
export type Transcript = string;
/**
 * Seconds from the start of the answer at which the word ends. Never earlier than start.
 */
export type End = number;
/**
 * Seconds from the start of the answer at which the word begins.
 */
export type Start = number;
/**
 * The spoken word as transcribed by the speech-to-text model.
 */
export type Word = string;
/**
 * Per-word timings in the order the words were spoken, used to compute pace and pauses. Empty when the speech-to-text source provides none.
 *
 * @maxItems 5000
 */
export type Words = WordTiming[];
/**
 * One or two sentences explaining why this score was given.
 */
export type Feedback = string;
/**
 * Whole-number score from 0 (very poor) to 10 (excellent).
 */
export type Score = number;
/**
 * The id of the question this evaluation grades.
 */
export type QuestionId = string;
/**
 * Overall feedback on the answer, with the most important improvement.
 */
export type Summary = string;
/**
 * Short, cleaned-up reason that grading failed, not the raw provider error. Present only when the status is grading_failed.
 */
export type GradingError = string | null;
/**
 * Difficulty from 1 (beginner) to 5 (expert).
 */
export type Difficulty = number;
/**
 * Globally unique identifier of the question, generated when it is created.
 */
export type Id1 = string;
/**
 * Stable identifier of the skill this question tests. The same skill keeps the same id across all preparations and sessions.
 */
export type SkillId = string;
/**
 * The question exactly as it is spoken to the candidate.
 */
export type Text = string;
/**
 * Where the turn is in its life cycle.
 */
export type TurnStatus = 'awaiting_answer' | 'awaiting_grade' | 'graded' | 'grading_failed';
/**
 * The turns of the interview, in the order the questions were asked.
 *
 * @maxItems 100
 */
export type Turns = Turn[];
/**
 * When the session last changed, used to resume or expire sessions.
 */
export type UpdatedAt = string;

/**
 * One practice attempt at an interview: an ordered list of turns.
 *
 * Many sessions can belong to the same preparation. The session is immutable:
 * to add a turn or change its status, call `updated()`, for example
 * `session.updated(turns=session.turns + (new_turn,))`.
 */
export interface InterviewSession {
  ended_at: EndedAt;
  id: Id;
  preparation_id: PreparationId;
  started_at: StartedAt;
  status: SessionStatus;
  turns: Turns;
  updated_at: UpdatedAt;
}
/**
 * One question-and-answer exchange in an interview session.
 *
 * A turn moves through the states described by TurnStatus, and the fields that
 * must be present depend on the state. A turn is immutable: to move it to its
 * next state, call `updated()`, which re-validates the result. Do not use
 * `model_copy(update=...)`, because it skips validation and can produce an
 * invalid turn.
 */
export interface Turn {
  /**
   * What the user said. Present once the user has answered.
   */
  answer: Answer | null;
  /**
   * The grade for the answer. Present only when the status is graded.
   */
  evaluation: Evaluation | null;
  grading_error: GradingError;
  question: Question;
  status: TurnStatus;
}
/**
 * What the user said in response to one interview question.
 */
export interface Answer {
  duration: Duration;
  transcript: Transcript;
  words: Words;
}
/**
 * One spoken word and when it was said within an answer.
 */
export interface WordTiming {
  end: End;
  start: Start;
  word: Word;
}
/**
 * The grade for one answer, scored on four metrics.
 */
export interface Evaluation {
  clarity: MetricScore;
  correctness: MetricScore1;
  depth: MetricScore2;
  question_id: QuestionId;
  relevance: MetricScore3;
  summary: Summary;
}
/**
 * How clearly and logically the answer is structured.
 */
export interface MetricScore {
  feedback: Feedback;
  score: Score;
}
/**
 * Whether the facts and reasoning in the answer are right.
 */
export interface MetricScore1 {
  feedback: Feedback;
  score: Score;
}
/**
 * How far the answer goes beyond surface-level knowledge.
 */
export interface MetricScore2 {
  feedback: Feedback;
  score: Score;
}
/**
 * How well the answer addresses the question and the role.
 */
export interface MetricScore3 {
  feedback: Feedback;
  score: Score;
}
/**
 * The question the interviewer asked.
 */
export interface Question {
  difficulty: Difficulty;
  id: Id1;
  skill_id: SkillId;
  text: Text;
}
