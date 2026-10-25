/* Generated from docs/schemas. Do not edit by hand. */

/**
 * Difficulty from 1 (beginner) to 5 (expert).
 */
export type Difficulty = number;
/**
 * Globally unique identifier of the question, generated when it is created.
 */
export type Id = string;
/**
 * Stable identifier of the skill this question tests. The same skill keeps the same id across all preparations and sessions.
 */
export type SkillId = string;
/**
 * The question exactly as it is spoken to the candidate.
 */
export type Text = string;

/**
 * One question the interviewer asks during a session.
 */
export interface Question {
  difficulty: Difficulty;
  id: Id;
  skill_id: SkillId;
  text: Text;
}
