// TypeScript mirrors of the backend Pydantic schemas (apps/backend/schemas.py)
// and the enums they reference (apps/backend/models.py). UUIDs and datetimes
// arrive as strings over JSON. Keep these in sync with the backend — it is the
// source of truth for shapes.

// --- Enums (models.py) -----------------------------------------------------

export type CellType = "code" | "notes";
export type SourceType = "pdf" | "text";
export type RequirementStatus = "not_started" | "in_progress" | "done";

// --- Read-side response models (schemas.py) --------------------------------

export type SessionRead = {
  id: string;
  title: string;
  created_at: string;
  modified_at: string;
  spec_id: string | null;
};

export type CellRead = {
  id: string;
  session_id: string;
  cell_type: CellType;
  language: string | null;
  content: string;
  last_output: string | null;
  status: string;
  order_index: number;
};

export type SpecRead = {
  id: string;
  source_type: SourceType;
  raw_text: string;
};

export type RequirementItemRead = {
  id: string;
  spec_id: string;
  text: string;
  status: RequirementStatus;
};

// The backend has no `EventRead`; the read-side of an Event is `TimelineEvent`
// (schemas.py), with its JSON payload already decoded into an object.
export type TimelineEvent = {
  id: string;
  session_id: string;
  timestamp: string;
  event_type: string;
  payload: Record<string, unknown>;
};

export type SessionTimeline = {
  session_id: string;
  events: TimelineEvent[];
  groups: Record<string, TimelineEvent[]>;
  // The session's current checklist; replay pairs it with requirement_status
  // events to reconstruct each item's check-off state at a past point.
  requirements: RequirementItemRead[];
};

// --- Write-side request models (schemas.py) --------------------------------

export type SessionCreate = {
  title?: string;
  spec_id?: string | null;
};

export type CellCreate = {
  session_id: string;
  cell_type?: CellType;
  language?: string | null;
  content?: string;
  order_index?: number | null;
};

export type CellUpdate = {
  content?: string;
  cell_type?: CellType;
  language?: string | null;
  order_index?: number | null;
};

export type RequirementUpdate = {
  status?: RequirementStatus;
  text?: string;
};

export type AttachSpecRequest = {
  spec_id: string;
};

export type SpecImportResponse = {
  spec_id: string;
  status: string;
};

// --- Practice: problems and course (routers/practice.py) -------------------

export type ProblemDifficulty = "easy" | "medium" | "hard";
export type ProblemSource = "builtin" | "generated";
export type ProblemStatus = "not_started" | "attempted" | "struggled" | "solved";

export type ProblemExample = {
  input: string;
  output: string;
  explanation: string;
};

export type ProblemRead = {
  id: string;
  slug: string;
  title: string;
  pattern: string;
  pattern_label: string;
  difficulty: ProblemDifficulty;
  prompt: string;
  examples: ProblemExample[];
  hints: string[];
  starter_code: string;
  language: string;
  source: ProblemSource;
  parent_problem_id: string | null;
  status: ProblemStatus;
  created_at: string;
};

export type ProblemUpdate = {
  status: ProblemStatus;
};

export type GenerateSimilarRequest = {
  note?: string | null;
  code?: string | null;
};

export type PracticeStartResponse = {
  session_id: string;
  spec_id: string;
};

export type LessonExercise = {
  description: string;
  starter_code: string;
  language: string;
};

export type LessonRead = {
  id: string;
  title: string;
  summary: string;
  body: string;
  exercise: LessonExercise;
  completed: boolean;
};

export type LessonProgressUpdate = {
  completed: boolean;
};

// --- AI co-pilot (routers/ai.py) -------------------------------------------

export type AiMode = "direct" | "socratic";

export type AskRequest = {
  session_id: string;
  cell_id?: string | null;
  question: string;
  mode: AiMode;
};

export type ExplainErrorResponse = {
  explanation: string;
};

export type ComplexityResponse = {
  analysis: string;
};

export type TranscribeResponse = {
  transcript: string;
};
