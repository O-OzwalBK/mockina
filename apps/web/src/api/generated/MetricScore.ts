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
 * A score for one grading metric, with the reasoning behind it.
 */
export interface MetricScore {
  feedback: Feedback;
  score: Score;
  [k: string]: unknown;
}
