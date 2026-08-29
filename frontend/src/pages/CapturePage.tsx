import { useEffect, useRef, useState } from "react";
import { confirmExperience, createAudioCapture, createTextCapture, getCaptureSession, patchDraft, patchCaptureSession, startReflection, submitAudioTurn, submitTextTurn } from "@/api/capture";
import { RequestError } from "@/api/client";
import type { CaptureSession } from "@/api/types";
import { ACTIVITY_NAME } from "@/lib/experience";
import { EXPERIENCE_FIELDS } from "@/lib/experience";
import type { ExperienceContent } from "@/api/types";
import micIllustration from "@/imports/capture-mic.svg";

export function CapturePage({ onConfirmed, onMarkerSaved, resumeSessionId }: { onConfirmed: () => void; onMarkerSaved: () => void; resumeSessionId?: string | null }) {
  const [text, setText] = useState("");
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [originalMarkerTranscript, setOriginalMarkerTranscript] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [question, setQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [draft, setDraft] = useState<ExperienceContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<"text" | "audio">("audio");
  const [answerInputMode, setAnswerInputMode] = useState<"text" | "audio">("text");
  const [recording, setRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null);
  const [recordedAnswerAudio, setRecordedAnswerAudio] = useState<Blob | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  useEffect(() => {
    const id = resumeSessionId ?? localStorage.getItem("practice-memory:last-session");
    if (!id) return;
    getCaptureSession(id).then((detail) => {
      if (detail.status !== "confirmed") {
        const latestQuestion = [...detail.conversation].reverse().find(
          (message) => message.role === "assistant" && message.kind === "question",
        );
        setSession(detail);
        setOriginalMarkerTranscript(detail.marker_transcript);
        setDraft(detail.draft);
        setQuestion(detail.status === "reflecting" ? latestQuestion?.text ?? null : null);
        setAnswer("");
      }
    }).catch(() => localStorage.removeItem("practice-memory:last-session"));
  }, [resumeSessionId]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function stopMediaStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  async function startRecording(target: "marker" | "answer") {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("当前浏览器不支持录音，请改用文字输入。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredType = ["audio/webm;codecs=opus", "audio/webm"].find(
        (type) => MediaRecorder.isTypeSupported(type),
      );
      const recorder = preferredType ? new MediaRecorder(stream, { mimeType: preferredType }) : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
      recorder.onstop = () => {
        const audio = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        setRecording(false);
        if (timerRef.current !== null) window.clearInterval(timerRef.current);
        timerRef.current = null;
        recorderRef.current = null;
        stopMediaStream();
        if (target === "marker") {
          setRecordedAudio(audio);
          void uploadRecording(audio);
        } else {
          setRecordedAnswerAudio(audio);
        }
      };
      streamRef.current = stream;
      recorderRef.current = recorder;
      setRecordingSeconds(0);
      recorder.start();
      setRecording(true);
      timerRef.current = window.setInterval(() => setRecordingSeconds((seconds) => seconds + 1), 1000);
    } catch {
      setError("未获得麦克风权限。请在浏览器地址栏允许麦克风后重试，或改用文字输入。");
      stopMediaStream();
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function uploadRecording(audio: Blob | null = recordedAudio) {
    if (!audio) return;
    if (audio.size > 15 * 1024 * 1024) {
      setError("录音超过 15 MiB，请缩短后重录。");
      return;
    }
    setTranscribing(true); setError(null);
    try {
      const created = await createAudioCapture(audio, ACTIVITY_NAME);
      localStorage.setItem("practice-memory:last-session", created.id);
      setRecordedAudio(null);
      onMarkerSaved();
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "录音上传失败，请重试。"); }
    finally { setTranscribing(false); }
  }

  async function submit() {
    setSubmitting(true); setError(null);
    try {
      const created = await createTextCapture(text.trim(), ACTIVITY_NAME);
      const detail = await getCaptureSession(created.id);
      setSession(detail); setOriginalMarkerTranscript(detail.marker_transcript); localStorage.setItem("practice-memory:last-session", created.id);
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "创建记录失败，请重试。"); }
    finally { setSubmitting(false); }
  }

  async function beginReflection() {
    if (!session) return;
    setSaving(true); setError(null);
    try {
      const transcript = session.marker_transcript?.trim() ?? "";
      if (transcript && transcript !== (originalMarkerTranscript?.trim() ?? "")) {
        const savedSession = await patchCaptureSession(session.id, transcript);
        setSession(savedSession);
        setOriginalMarkerTranscript(savedSession.marker_transcript);
      }
      const result = await startReflection(session.id);
      const refreshed = await getCaptureSession(session.id);
      setSession(refreshed);
      setOriginalMarkerTranscript(refreshed.marker_transcript);
      setQuestion(result.next_question?.text ?? null);
      setDraft(result.draft);
    }
    catch (reason) { setError(reason instanceof RequestError ? reason.message : "AI 复盘启动失败，请重试。"); }
    finally { setSaving(false); }
  }

  async function sendAnswer() {
    if (!session || !answer.trim()) return;
    setSaving(true); setError(null);
    try { const result = await submitTextTurn(session.id, answer.trim()); setAnswer(""); setSession((current) => current ? { ...current, status: result.status, draft: result.draft } : current); setQuestion(result.next_question?.text ?? null); setDraft(result.draft); }
    catch (reason) { setError(reason instanceof RequestError ? reason.message : "提交回答失败，请重试。"); }
    finally { setSaving(false); }
  }

  async function uploadAnswerRecording() {
    if (!session || !recordedAnswerAudio) return;
    if (recordedAnswerAudio.size > 15 * 1024 * 1024) {
      setError("录音超过 15 MiB，请缩短后重录。");
      return;
    }
    setSaving(true); setError(null);
    try {
      const result = await submitAudioTurn(session.id, recordedAnswerAudio);
      setRecordedAnswerAudio(null);
      setSession((current) => current ? { ...current, status: result.status, draft: result.draft } : current);
      setQuestion(result.next_question?.text ?? null);
      setDraft(result.draft);
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "语音回答提交失败，请重试。"); }
    finally { setSaving(false); }
  }

  if (session && draft) return <section className="space-y-4 px-5 py-6"><p className="text-xs font-bold text-leaf">AI 已整理完成 · 请确认</p><h1 className="font-display text-3xl font-extrabold text-ink">经验卡片</h1>{EXPERIENCE_FIELDS.map(([key, label]) => <label key={key} className="block space-y-1"><span className="text-sm font-bold">{label}</span><textarea value={draft[key] ?? ""} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} rows={3} className="w-full resize-none rounded-xl border-2 border-ink bg-cream p-3 text-sm" /></label>)}<button onClick={async () => { if (!session || !draft) return; setSaving(true); setError(null); try { await patchDraft(session.id, draft); await confirmExperience(session.id); localStorage.removeItem("practice-memory:last-session"); onConfirmed(); } catch (reason) { setError(reason instanceof RequestError ? reason.message : "确认失败，请重试。"); } finally { setSaving(false); } }} disabled={saving} className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 font-bold">{saving ? "确认中…" : "确认保存经验卡片"}</button>{error && <p className="text-sm text-red-700">{error}</p>}</section>;

  if (session) return <section className="space-y-5 px-5 py-6">
    <p className="text-xs font-bold text-leaf">儿童阅读活动 · 待整理</p>
    <h1 className="font-display text-3xl font-extrabold text-ink">检查这条记录</h1>
    <p className="text-sm text-ink-soft">确认无误后，再交给 AI 复盘。原始事实可以先由你修改。</p>
    <textarea value={session.marker_transcript ?? ""} onChange={(event) => setSession({ ...session, marker_transcript: event.target.value })} rows={8}
      className="w-full resize-none rounded-2xl border-2 border-ink bg-cream p-4 text-sm outline-none focus:border-leaf" />
    {error && <p className="text-sm font-bold text-red-700">{error}</p>}
    {!question ? (
      <button onClick={beginReflection} disabled={saving} className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a] disabled:opacity-60">{saving ? "AI 正在整理…" : "开始 AI 复盘"}</button>
    ) : (
      <div className="space-y-3 rounded-2xl border-2 border-ink bg-lime-wash p-4">
        <p className="text-sm font-bold">AI：{question}</p>
        <div className="grid grid-cols-2 gap-2 rounded-xl bg-cream/70 p-1 text-sm font-bold">
          <button onClick={() => setAnswerInputMode("text")} className={`rounded-lg px-3 py-2 ${answerInputMode === "text" ? "bg-cream shadow-sm" : "text-ink-soft"}`}>文字回答</button>
          <button onClick={() => setAnswerInputMode("audio")} className={`rounded-lg px-3 py-2 ${answerInputMode === "audio" ? "bg-cream shadow-sm" : "text-ink-soft"}`}>语音回答</button>
        </div>
        {answerInputMode === "text" ? (
          <>
            <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={4} placeholder="用文字回答" className="w-full resize-none rounded-xl border-2 border-ink bg-cream p-3 text-sm outline-none" />
            <button onClick={sendAnswer} disabled={!answer.trim() || saving} className="w-full rounded-full border-2 border-ink bg-lime px-4 py-2 text-sm font-bold disabled:opacity-60">{saving ? "提交中…" : "提交回答"}</button>
          </>
        ) : (
          <div className="space-y-2 rounded-xl border-2 border-ink bg-cream p-3">
            <p className="text-center font-display text-2xl font-extrabold text-ink">{String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:{String(recordingSeconds % 60).padStart(2, "0")}</p>
            {!recording ? <button onClick={() => startRecording("answer")} disabled={saving} className="w-full rounded-full border-2 border-ink bg-lime px-4 py-2 text-sm font-bold">{recordedAnswerAudio ? "重新录制" : "开始录音"}</button> : <button onClick={stopRecording} className="w-full rounded-full border-2 border-ink bg-red-100 px-4 py-2 text-sm font-bold">停止录音</button>}
            {recordedAnswerAudio && !recording && <button onClick={uploadAnswerRecording} disabled={saving} className="w-full rounded-full border-2 border-ink bg-lime px-4 py-2 text-sm font-bold">{saving ? "正在转写…" : "提交语音回答"}</button>}
          </div>
        )}
      </div>
    )}
  </section>;

  return <section className="flex min-h-full flex-col px-5 pb-6 pt-3">
    <button onClick={() => setInputMode("audio")} className="flex items-center gap-3 rounded-2xl border-2 border-ink/15 bg-cream px-4 py-3 text-left">
      <span className="text-lg">🎧</span><span className="flex-1"><span className="block text-sm font-bold">语音记录</span><span className="block text-xs text-ink-soft">单段录音 · 转写后可修改</span></span><span className="text-ink-soft">⌄</span>
    </button>
    {inputMode === "audio" ? <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
      <button onClick={() => recording ? stopRecording() : startRecording("marker")} disabled={transcribing} className="relative h-[216px] w-[216px] disabled:opacity-60" aria-label={recording ? "停止录音" : "开始语音记录"}>
        {recording && <><span className="animate-ring absolute inset-0 rounded-full bg-lime/70" /><span className="animate-ring absolute inset-0 rounded-full bg-lime/70" style={{ animationDelay: "1.1s" }} /></>}
        <img src={micIllustration} alt="" className="relative block h-full w-full" />
      </button>
      <p className="mt-6 font-display text-xl font-extrabold text-ink">{recording ? `${String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:${String(recordingSeconds % 60).padStart(2, "0")}` : transcribing ? "正在保存到待处理…" : recordedAudio ? "录音保存未完成" : "点击开始语音记录"}</p>
      <p className="mt-2 text-xs text-ink-soft">录音仅用于转写，并按后端清理策略删除</p>
    </div> : <div className="flex flex-1 flex-col justify-center py-8"><label className="block space-y-2"><span className="text-sm font-bold text-ink">这次发生了什么？</span><textarea value={text} onChange={(event) => setText(event.target.value)} rows={8} placeholder="例如：三个孩子站在门口，没有进入共读区域……" className="w-full resize-none rounded-2xl border-2 border-ink bg-cream p-4 text-sm outline-none focus:border-leaf" /></label></div>}
    {error && <p className="mb-3 text-sm font-bold text-red-700">{error}</p>}
    <div className="space-y-3">
      {inputMode === "audio" ? (transcribing || recordedAudio ? <button onClick={() => void uploadRecording()} disabled={recording || transcribing} className="w-full rounded-full border-2 border-ink bg-ink px-5 py-3 text-sm font-bold text-cream shadow-[3px_3px_0_0_#1c2b0a] disabled:cursor-not-allowed disabled:border-ink/10 disabled:bg-ink/10 disabled:text-ink-soft">{transcribing ? "正在保存…" : "重新上传这段录音"}</button> : null) : <button onClick={submit} disabled={!text.trim() || submitting} className="w-full rounded-full border-2 border-ink bg-ink px-5 py-3 text-sm font-bold text-cream shadow-[3px_3px_0_0_#1c2b0a] disabled:cursor-not-allowed disabled:border-ink/10 disabled:bg-ink/10 disabled:text-ink-soft">{submitting ? "正在保存…" : "下一步：检查记录"}</button>}
      <button onClick={() => { setInputMode(inputMode === "audio" ? "text" : "audio"); setError(null); }} disabled={recording || transcribing} className="w-full rounded-2xl border border-ink/40 bg-cream px-4 py-3 text-left text-sm text-ink-soft disabled:cursor-not-allowed disabled:opacity-50">{inputMode === "audio" ? "改用文字输入" : "返回语音记录"}</button>
    </div>
  </section>;
}
