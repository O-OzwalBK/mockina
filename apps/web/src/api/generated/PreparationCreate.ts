/* Generated from docs/schemas. Do not edit by hand. */

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
 * What a client sends to start preparing for a job.
 */
export interface PreparationCreate {
  job_description: JobDescription;
  job_title: JobTitle;
  resume?: Resume;
}
