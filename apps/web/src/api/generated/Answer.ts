/* Generated from docs/schemas. Do not edit by hand. */

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
