import { api, apiVoid } from "./client";
import type { CaptureSession, CaptureSessionCreated, DecisionSupportResponse, ExperienceContent, ReflectionResponse, TurnResponse } from "./types";

export function createTextCapture(text: string, activityName: string) {
  const body = new FormData();
  body.set("text", text);
  body.set("activity_name", activityName);
  body.set("entry_mode", "marker");
  return api<CaptureSessionCreated>("/capture-sessions", { method: "POST", body });
}

export function createAudioCapture(audio: Blob, activityName: string) {
  const body = new FormData();
  body.set("audio", audio, "quick-marker.webm");
  body.set("activity_name", activityName);
  body.set("entry_mode", "marker");
  return api<CaptureSessionCreated>("/capture-sessions", { method: "POST", body });
}

export function getCaptureSession(sessionId: string) {
  return api<CaptureSession>(`/capture-sessions/${sessionId}`);
}

export function patchCaptureSession(sessionId: string, markerTranscript: string) {
  return api<CaptureSession>(`/capture-sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ marker_transcript: markerTranscript }),
  });
}

export function startReflection(sessionId: string) {
  return api<ReflectionResponse>(`/capture-sessions/${sessionId}/start-reflection`, { method: "POST" });
}

export function submitTextTurn(sessionId: string, text: string) {
  const body = new FormData();
  body.set("text", text);
  return api<TurnResponse>(`/capture-sessions/${sessionId}/turns`, { method: "POST", body });
}

export function submitAudioTurn(sessionId: string, audio: Blob) {
  const body = new FormData();
  body.set("audio", audio, "reflection-answer.webm");
  return api<TurnResponse>(`/capture-sessions/${sessionId}/turns`, { method: "POST", body });
}

export function patchDraft(sessionId: string, draft: ExperienceContent) {
  return api<CaptureSession>(`/capture-sessions/${sessionId}/draft`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
}

export function confirmExperience(sessionId: string) {
  return api(`/capture-sessions/${sessionId}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ contributor_name: "当前演示贡献者", contributor_role: "乡村图书馆员" }) });
}

export type CaptureSessionSummary = {
  id: string;
  activity_name: string | null;
  marker_transcript_preview: string | null;
  status: "marked" | "reflecting" | "needs_confirmation" | "confirmed" | "failed";
  captured_at: string;
};

export function listPendingSessions() {
  return api<CaptureSessionSummary[]>("/capture-sessions?limit=20");
}

export function deleteCaptureSession(sessionId: string) {
  return apiVoid(`/capture-sessions/${sessionId}`, { method: "DELETE" });
}

export function deleteExperience(experienceId: string) {
  return apiVoid(`/experiences/${experienceId}`, { method: "DELETE" });
}

export function listExperiences() {
  return api<Array<ExperienceContent & { id: string; recorded_at: string }>>("/experiences?activity_name=%E4%BA%B2%E5%AD%90%E5%85%B1%E8%AF%BB%E6%B4%BB%E5%8A%A8&limit=20");
}

export function requestDecisionSupport(concern: string) {
  const body = new FormData();
  body.set("activity_name", "亲子共读活动");
  body.set("text", concern);
  return api<DecisionSupportResponse>("/decision-support", { method: "POST", body });
}

export function requestAudioDecisionSupport(audio: Blob) {
  const body = new FormData();
  body.set("activity_name", "亲子共读活动");
  body.set("audio", audio, "decision-support.webm");
  return api<DecisionSupportResponse>("/decision-support", { method: "POST", body });
}
