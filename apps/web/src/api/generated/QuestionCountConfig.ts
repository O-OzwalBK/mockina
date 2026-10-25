/* Generated from docs/schemas. Do not edit by hand. */

/**
 * Number of questions to ask before the interview ends.
 */
export type Count = number;
/**
 * Which end rule this configuration uses.
 */
export type Rule = 'question_count';

/**
 * End the interview after a fixed number of questions.
 */
export interface QuestionCountConfig {
  count: Count;
  rule: Rule;
}
