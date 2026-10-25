/* Generated from docs/schemas. Do not edit by hand. */

/**
 * Total time spent answering, in seconds, before the interview ends.
 */
export type MaxSeconds = number;
/**
 * Which end rule this configuration uses.
 */
export type Rule = 'answer_time';

/**
 * End the interview once the answers add up to a time limit.
 */
export interface AnswerTimeConfig {
  max_seconds: MaxSeconds;
  rule: Rule;
}
