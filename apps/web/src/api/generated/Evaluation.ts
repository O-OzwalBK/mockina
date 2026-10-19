/* Generated from docs/schemas. Do not edit by hand. */

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
 * The grade for one answer, scored on four metrics.
 */
export interface Evaluation {
  clarity: MetricScore;
  correctness: MetricScore1;
  depth: MetricScore2;
  question_id: QuestionId;
  relevance: MetricScore3;
  summary: Summary;
  [k: string]: unknown;
}
/**
 * How clearly and logically the answer is structured.
 */
export interface MetricScore {
  feedback: Feedback;
  score: Score;
  [k: string]: unknown;
}
/**
 * Whether the facts and reasoning in the answer are right.
 */
export interface MetricScore1 {
  feedback: Feedback;
  score: Score;
  [k: string]: unknown;
}
/**
 * How far the answer goes beyond surface-level knowledge.
 */
export interface MetricScore2 {
  feedback: Feedback;
  score: Score;
  [k: string]: unknown;
}
/**
 * How well the answer addresses the question and the role.
 */
export interface MetricScore3 {
  feedback: Feedback;
  score: Score;
  [k: string]: unknown;
}
