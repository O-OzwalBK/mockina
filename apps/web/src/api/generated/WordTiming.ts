/* Generated from docs/schemas. Do not edit by hand. */

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
 * One spoken word and when it was said within an answer.
 */
export interface WordTiming {
  end: End;
  start: Start;
  word: Word;
}
