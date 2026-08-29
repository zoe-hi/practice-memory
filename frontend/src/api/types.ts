export type CaptureStatus = "marked" | "reflecting" | "needs_confirmation" | "confirmed" | "failed";

export type ExperienceContent = {
  context: string | null;
  action_and_reason: string | null;
  observed_result: string | null;
  went_well: string | null;
  shortcomings: string | null;
  things_to_note: string | null;
  open_question: string | null;
};

export type ConversationMessage = {
  turn_id: string;
  role: "user" | "assistant";
  kind: "marker" | "question" | "answer";
  text: string;
  source: "audio" | "text" | "generated";
  created_at: string;
};

export type CaptureSession = ExperienceContent & {
  id: string;
  activity_name: string | null;
  marker_transcript: string | null;
  status: CaptureStatus;
  conversation: ConversationMessage[];
  draft: ExperienceContent | null;
  can_confirm: boolean;
  captured_at: string;
  updated_at: string;
  expires_at: string;
};

export type ApiError = { code: string; message: string; retryable: boolean };

export type CaptureSessionCreated = {
  id: string;
  activity_name: string | null;
  status: CaptureStatus;
  marker_transcript: string | null;
};

export type ExperienceResponse = ExperienceContent & {
  id: string;
  activity_name: string;
  contributor_name: string;
  contributor_role: string | null;
  recorded_at: string;
  updated_at: string;
};

export type DecisionSupportResponse = {
  activity_name: string;
  concern_transcript: string;
  understanding: string;
  match: { experience: ExperienceResponse; why_similar: string } | null;
  considerations: Array<{ direction: string; tradeoff: string | null; basis_experience_id: string }>;
  question_to_consider: string | null;
};
