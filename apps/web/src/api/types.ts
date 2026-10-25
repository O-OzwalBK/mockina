import type { Answer } from "./generated/Answer";
import type { Evaluation } from "./generated/Evaluation";
import type { InterviewSession } from "./generated/InterviewSession";
import type { MetricScore } from "./generated/MetricScore";
import type { Preparation } from "./generated/Preparation";
import type { PreparationCreate } from "./generated/PreparationCreate";
import type { Question } from "./generated/Question";
import type { Turn } from "./generated/Turn";
import type { WordTiming } from "./generated/WordTiming";

export type {
  Answer,
  Evaluation,
  InterviewSession,
  MetricScore,
  Preparation,
  PreparationCreate,
  Question,
  Turn,
  WordTiming,
};

export interface Identity {
  user_id: string;
  token: string;
  created_at: string;
}

export interface Capabilities {
  anonymous_retention_days: number;
  hosted_stt: boolean;
  dev_routes: boolean;
  limits: {
    max_job_title_length: number;
    max_job_description_length: number;
    max_resume_length: number;
    max_transcript_length: number;
    max_words_per_answer: number;
    max_word_length: number;
    max_answer_seconds: number;
  };
}

export interface PreparationSummary {
  id: string;
  job_title: string;
  created_at: string;
  session_count: number;
  last_session_at: string | null;
}

export interface SessionSummary {
  id: string;
  preparation_id: string;
  status: "in_progress" | "completed" | "abandoned";
  started_at: string;
  ended_at: string | null;
  turns_total: number;
  turns_graded: number;
}

export interface JobPresetSummary {
  id: string;
  job_title: string;
  category: string;
}

export interface JobPreset extends JobPresetSummary {
  job_description: string;
}

export interface AnswerReceipt {
  question_id: string;
  status: "awaiting_grade" | "graded" | "grading_failed";
}

export interface GradingStatus {
  session_status: SessionSummary["status"];
  turns: Array<{
    question_id: string;
    status: Turn["status"];
    grading_error: string | null;
  }>;
}

export interface SkillProgress {
  id: string;
  label: string;
  parent_id: string | null;
  mastery: number | null;
  evidence_count: number;
  last_practiced_at: string | null;
}

export interface Progress {
  summary: {
    sessions_completed: number;
    answers_graded: number;
    metric_averages: Record<
      "correctness" | "depth" | "clarity" | "relevance",
      number
    >;
  };
  metric_trend: Array<{
    session_id: string;
    ended_at: string;
    correctness: number;
    depth: number;
    clarity: number;
    relevance: number;
  }>;
  skills: SkillProgress[];
  weakest_skill_ids: string[];
  strongest_skill_ids: string[];
  tips: Array<{ skill_id: string; text: string }>;
}

export interface DevModelInfo {
  model: string;
  host: string;
  context_tokens: number;
  max_output_tokens: number;
  api_key_set: boolean;
}

export interface CompletionRequest {
  messages: Array<{ role: "system" | "user" | "assistant"; content: string }>;
  temperature?: number;
  max_output_tokens?: number;
}

export interface CompletionResponse {
  text: string;
  model: string;
  finish_reason: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  elapsed_ms: number;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    details: Record<string, unknown>;
  };
}

export interface ValidationIssue {
  loc: Array<string | number>;
  msg: string;
  type: string;
}
