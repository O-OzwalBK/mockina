/* Generated from docs/schemas. Do not edit by hand. */

/**
 * When the preparation was created, as a timezone-aware UTC time.
 */
export type CreatedAt = string;
/**
 * Globally unique identifier of the preparation, generated when it is created.
 */
export type Id = string;
/**
 * Full text of the job description, pasted by the user or taken from a preset.
 */
export type JobDescription = string;
/**
 * Short name for the target job, shown when listing preparations.
 */
export type JobTitle = string;
/**
 * Optional resume text. Omit it or send null when there is none.
 */
export type Resume = string | null;

/**
 * A stored preparation: what the client sent, plus the fields the server owns.
 */
export interface Preparation {
  created_at: CreatedAt;
  id: Id;
  job_description: JobDescription;
  job_title: JobTitle;
  resume: Resume;
}
