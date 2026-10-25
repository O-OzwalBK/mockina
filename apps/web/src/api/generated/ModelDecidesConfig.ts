/* Generated from docs/schemas. Do not edit by hand. */

/**
 * Largest number of questions the model may ask before code forces a finish.
 */
export type MaxQuestions = number;
/**
 * Smallest number of questions before the model may decide to finish.
 */
export type MinQuestions = number;
/**
 * Which end rule this configuration uses.
 */
export type Rule = 'model_decides';

/**
 * The model decides when to finish, between a minimum and a maximum.
 */
export interface ModelDecidesConfig {
  max_questions: MaxQuestions;
  min_questions: MinQuestions;
  rule: Rule;
}
