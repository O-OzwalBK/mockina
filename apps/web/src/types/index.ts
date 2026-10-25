export type Preparation = {
  id: string;
  title: string;
  level: string;
  questionCount: number;
  progress: number;
};
export type InterviewSession = {
  id: string;
  preparationId: string;
  status: "ready" | "in_progress" | "grading" | "complete";
};
export type InterviewReport = {
  id: string;
  sessionId: string;
  strengths: string[];
  improvements: string[];
};
