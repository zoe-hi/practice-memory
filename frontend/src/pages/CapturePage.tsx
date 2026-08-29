import { useEffect, useRef, useState } from "react";
import { confirmExperience, createAudioCapture, createTextCapture, getCaptureSession, patchDraft, patchCaptureSession, startReflection, submitAudioTurn, submitTextTurn } from "@/api/capture";
import { RequestError } from "@/api/client";
import type { CaptureSession, TurnResponse } from "@/api/types";
import { ACTIVITY_NAME } from "@/lib/experience";
import { EXPERIENCE_FIELDS } from "@/lib/experience";
import type { ExperienceContent } from "@/api/types";
import micIllustration from "@/imports/capture-mic.svg";
import successIcon from "@/imports/success-icon.svg";

export function CapturePage({ onConfirmed, onMarkerSaved, onExit, resumeSessionId }: { onConfirmed: () => void; onMarkerSaved: () => void; onExit: () => void; resumeSessionId?: string | null }) {
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
  const [justConfirmed, setJustConfirmed] = useState(false);
  const [editingCard, setEditingCard] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    // Only resume when the user explicitly picked a session from 我的.
    // 记一下 (no resumeSessionId) always opens a fresh recorder.
    if (!resumeSessionId) return;
    getCaptureSession(resumeSessionId).then((detail) => {
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
    }).catch(() => setError("无法读取这条记录，请回到“我的”重试。"));
  }, [resumeSessionId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [session?.conversation.length, question]);

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

  function captureNext() {
    setJustConfirmed(false);
    setSession(null);
    setOriginalMarkerTranscript(null);
    setDraft(null);
    setQuestion(null);
    setAnswer("");
    setText("");
    setRecordedAudio(null);
    setRecordedAnswerAudio(null);
    setError(null);
    setInputMode("audio");
  }

  async function uploadRecording(audio: Blob | null = recordedAudio) {
    if (!audio) return;
    if (audio.size > 15 * 1024 * 1024) {
      setError("录音超过 15 MiB，请缩短后重录。");
      return;
    }
    setTranscribing(true); setError(null);
    try {
      await createAudioCapture(audio, ACTIVITY_NAME);
      setRecordedAudio(null);
      onMarkerSaved();
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "录音上传失败，请重试。"); }
    finally { setTranscribing(false); }
  }

  async function startTextReflection() {
    if (!text.trim()) return;
    setSubmitting(true); setError(null);
    try {
      const created = await createTextCapture(text.trim(), ACTIVITY_NAME);
      const result = await startReflection(created.id);
      const detail = await getCaptureSession(created.id);
      setSession(detail);
      setOriginalMarkerTranscript(detail.marker_transcript);
      setQuestion(result.next_question?.text ?? null);
      setDraft(result.draft);
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "AI 复盘启动失败，请重试。"); }
    finally { setSubmitting(false); }
  }

  async function saveTextForLater() {
    if (!text.trim()) return;
    setSubmitting(true); setError(null);
    try {
      await createTextCapture(text.trim(), ACTIVITY_NAME);
      onMarkerSaved();
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "保存失败，请重试。"); }
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

  function appendTurn(current: CaptureSession | null, result: TurnResponse, answerSource: "text" | "audio"): CaptureSession | null {
    if (!current) return current;
    const now = new Date().toISOString();
    const messages = [...current.conversation];
    if (result.answer_transcript) {
      messages.push({ turn_id: `${now}-answer`, role: "user", kind: "answer", text: result.answer_transcript, source: answerSource, created_at: now });
    }
    if (result.next_question) {
      messages.push({ turn_id: result.next_question.turn_id, role: "assistant", kind: "question", text: result.next_question.text, source: "generated", created_at: now });
    }
    return { ...current, status: result.status, draft: result.draft, conversation: messages };
  }

  async function sendAnswer() {
    if (!session || !answer.trim()) return;
    setSaving(true); setError(null);
    try { const result = await submitTextTurn(session.id, answer.trim()); setAnswer(""); setSession((current) => appendTurn(current, result, "text")); setQuestion(result.next_question?.text ?? null); setDraft(result.draft); }
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
      setSession((current) => appendTurn(current, result, "audio"));
      setQuestion(result.next_question?.text ?? null);
      setDraft(result.draft);
    } catch (reason) { setError(reason instanceof RequestError ? reason.message : "语音回答提交失败，请重试。"); }
    finally { setSaving(false); }
  }

  if (justConfirmed) return <section className="flex min-h-full flex-col items-center justify-center px-6 py-10 text-center">
    <span className="flex h-24 w-24 items-center justify-center rounded-full border-2 border-ink bg-lime shadow-[4px_4px_0_0_#1c2b0a]">
      <img src={successIcon} alt="" className="h-9 w-9" />
    </span>
    <h1 className="mt-6 font-display text-3xl font-extrabold text-ink">已保存！</h1>
    <p className="mt-2 max-w-[16rem] text-sm text-ink-soft">这条经验已进入“我的”，之后遇到相近现场可以带回来参考。</p>
    <div className="mt-8 w-full max-w-[20rem] space-y-3">
      <button onClick={onConfirmed} className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a]">去“我的”看看</button>
      <button onClick={captureNext} className="w-full rounded-full border-2 border-ink bg-cream px-5 py-3 text-sm font-bold">再记一条</button>
    </div>
  </section>;

  if (session && draft && session.status === "needs_confirmation") {
    const filledFields = EXPERIENCE_FIELDS.filter(([key]) => (draft[key] ?? "").trim().length > 0);
    return <section className="space-y-4 px-5 py-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold text-leaf">AI 已整理完成 · 请确认</p>
          <h1 className="mt-1 font-display text-3xl font-extrabold text-ink">经验卡片</h1>
        </div>
        <button onClick={() => setEditingCard((v) => !v)} className="mt-1 shrink-0 rounded-full border-2 border-ink bg-cream px-4 py-1.5 text-xs font-bold shadow-[2px_2px_0_0_#1c2b0a]">{editingCard ? "完成编辑" : "编辑"}</button>
      </div>
      {editingCard ? (
        <div className="space-y-3">{EXPERIENCE_FIELDS.map(([key, label]) => <label key={key} className="block space-y-1"><span className="text-sm font-bold">{label}</span><textarea value={draft[key] ?? ""} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} rows={3} placeholder="（留空则不收录这一项）" className="w-full resize-none rounded-xl border-2 border-ink bg-cream p-3 text-sm outline-none focus:border-leaf" /></label>)}</div>
      ) : (
        <article className="overflow-hidden rounded-2xl border-2 border-ink bg-cream shadow-[3px_3px_0_0_#1c2b0a]">
          <div className="border-b-2 border-ink bg-lime px-4 py-3"><p className="text-xs font-bold text-ink/70">儿童阅读活动 · 一条经验</p><h2 className="mt-0.5 font-bold leading-snug text-ink">{draft.context?.trim() || "一条待确认经验"}</h2></div>
          <div className="divide-y divide-ink/10">
            {filledFields.length === 0
              ? <p className="px-4 py-4 text-sm text-ink-soft">AI 还没能整理出内容，点“编辑”补充，或返回复盘再补几句。</p>
              : filledFields.map(([key, label]) => <div key={key} className="px-4 py-3"><p className="text-xs font-bold tracking-wide text-leaf">{label}</p><p className="mt-1 text-sm leading-6 text-ink">{draft[key]}</p></div>)}
          </div>
        </article>
      )}
      <button onClick={async () => { if (!session || !draft) return; setSaving(true); setError(null); try { await patchDraft(session.id, draft); await confirmExperience(session.id); setJustConfirmed(true); } catch (reason) { setError(reason instanceof RequestError ? reason.message : "确认失败，请重试。"); } finally { setSaving(false); } }} disabled={saving} className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 font-bold shadow-[3px_3px_0_0_#1c2b0a] disabled:opacity-60">{saving ? "确认中…" : "确认保存经验卡片"}</button>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </section>;
  }

  if (session && session.status !== "reflecting" && !question) return <section className="space-y-5 px-5 py-6">
    <p className="text-xs font-bold text-leaf">儿童阅读活动 · 待整理</p>
    <h1 className="font-display text-3xl font-extrabold text-ink">检查这条记录</h1>
    <p className="text-sm text-ink-soft">确认无误后，再交给 AI 复盘。原始事实可以先由你修改。</p>
    <textarea value={session.marker_transcript ?? ""} onChange={(event) => setSession({ ...session, marker_transcript: event.target.value })} rows={8}
      className="w-full resize-none rounded-2xl border-2 border-ink bg-cream p-4 text-sm outline-none focus:border-leaf" />
    {error && <p className="text-sm font-bold text-red-700">{error}</p>}
    <button onClick={beginReflection} disabled={saving} className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a] disabled:opacity-60">{saving ? "AI 正在整理…" : "开始 AI 复盘"}</button>
    <button onClick={onExit} disabled={saving} className="w-full rounded-full border-2 border-ink/40 bg-cream px-5 py-3 text-sm font-bold text-ink-soft disabled:opacity-60">稍后再说</button>
    <p className="text-center text-xs text-ink-soft">这条记录会保留在“我的”，随时可以回来继续。</p>
  </section>;

  if (session) return <section className="flex min-h-full flex-col">
    <div className="shrink-0 border-b-2 border-ink/10 bg-cream/95 px-5 py-3 backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold text-leaf">AI 复盘 · 儿童阅读活动</p>
          <h1 className="font-display text-lg font-extrabold text-ink">一次一个问题，聊清楚经过</h1>
        </div>
        <button onClick={onExit} className="shrink-0 rounded-full border-2 border-ink/40 bg-cream px-3 py-1.5 text-xs font-bold text-ink-soft">稍后再说</button>
      </div>
    </div>
    <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
      {session.conversation.map((message) => message.role === "assistant" ? (
        <div key={message.turn_id} className="flex justify-start">
          <div className="max-w-[85%] rounded-2xl rounded-tl-md border-2 border-ink bg-lime-wash px-4 py-2.5 text-sm leading-6 text-ink shadow-[2px_2px_0_0_#1c2b0a]">
            <span className="mb-0.5 block text-[10px] font-bold tracking-wide text-leaf">{message.kind === "marker" ? "你的记录" : "AI 提问"}</span>
            {message.text}
          </div>
        </div>
      ) : (
        <div key={message.turn_id} className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-tr-md border-2 border-ink bg-lime px-4 py-2.5 text-sm leading-6 text-ink shadow-[2px_2px_0_0_#1c2b0a]">{message.text}</div>
        </div>
      ))}
      {saving && <div className="flex justify-start"><div className="rounded-2xl rounded-tl-md border-2 border-ink/30 bg-cream px-4 py-2.5 text-sm text-ink-soft">AI 正在思考…</div></div>}
      <div ref={chatEndRef} />
    </div>
    <div className="shrink-0 space-y-2 border-t-2 border-ink/10 bg-cream/95 px-5 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur">
      {error && <p className="text-sm font-bold text-red-700">{error}</p>}
      {answerInputMode === "text" ? (
        <div className="flex items-end gap-2">
          <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={1} placeholder="输入你的回答…" className="max-h-32 min-h-[46px] flex-1 resize-none rounded-2xl border-2 border-ink bg-cream px-4 py-2.5 text-sm outline-none focus:border-leaf" />
          <button onClick={sendAnswer} disabled={!answer.trim() || saving} className="h-[46px] shrink-0 rounded-full border-2 border-ink bg-lime px-5 text-sm font-bold shadow-[2px_2px_0_0_#1c2b0a] disabled:cursor-not-allowed disabled:border-ink/10 disabled:bg-ink/10 disabled:text-ink-soft">发送</button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 py-1">
          {recordedAnswerAudio && !recording ? (
            <div className="flex w-full items-center gap-2">
              <button onClick={uploadAnswerRecording} disabled={saving} className="h-[46px] flex-1 rounded-full border-2 border-ink bg-lime px-5 text-sm font-bold shadow-[2px_2px_0_0_#1c2b0a] disabled:opacity-60">{saving ? "正在提交…" : "发送这段语音"}</button>
              <button onClick={() => setRecordedAnswerAudio(null)} disabled={saving} className="h-[46px] shrink-0 rounded-full border-2 border-ink/40 bg-cream px-4 text-sm font-bold text-ink-soft disabled:opacity-60">重录</button>
            </div>
          ) : (
            <button onClick={() => recording ? stopRecording() : startRecording("answer")} className={`flex h-[46px] w-full items-center justify-center gap-2 rounded-full border-2 border-ink px-5 text-sm font-bold shadow-[2px_2px_0_0_#1c2b0a] ${recording ? "bg-lime" : "bg-cream"}`}>{recording ? `● 停止录音 · ${String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:${String(recordingSeconds % 60).padStart(2, "0")}` : "🎤 按住说完点停止"}</button>
          )}
        </div>
      )}
      <button onClick={() => { setAnswerInputMode(answerInputMode === "text" ? "audio" : "text"); setError(null); }} disabled={recording || saving} className="w-full text-center text-xs font-bold text-ink-soft disabled:opacity-50">{answerInputMode === "text" ? "改用语音回答" : "改用文字回答"}</button>
    </div>
  </section>;

  return <section className="flex min-h-full flex-col px-5 pb-6 pt-3">
    <div className="flex gap-2 rounded-full border-2 border-ink bg-cream p-1 shadow-[2px_2px_0_0_#1c2b0a]">
      {([["audio", "🎧 语音"], ["text", "✍️ 文字"]] as const).map(([mode, label]) => (
        <button
          key={mode}
          onClick={() => { setInputMode(mode); setError(null); }}
          disabled={recording || transcribing}
          className={`flex-1 rounded-full px-4 py-2 text-sm font-bold transition disabled:opacity-50 ${inputMode === mode ? "bg-lime text-ink shadow-[2px_2px_0_0_#1c2b0a]" : "text-ink-soft"}`}
        >
          {label}
        </button>
      ))}
    </div>
    {inputMode === "audio" ? <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
      <button onClick={() => recording ? stopRecording() : startRecording("marker")} disabled={transcribing} className="relative h-[216px] w-[216px] disabled:opacity-60" aria-label={recording ? "停止录音" : "开始语音记录"}>
        {recording && <><span className="animate-ring absolute inset-0 rounded-full bg-lime/70" /><span className="animate-ring absolute inset-0 rounded-full bg-lime/70" style={{ animationDelay: "1.1s" }} /></>}
        <img src={micIllustration} alt="" className="relative block h-full w-full" />
      </button>
      <p className="mt-6 font-display text-xl font-extrabold text-ink">{recording ? `${String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:${String(recordingSeconds % 60).padStart(2, "0")}` : transcribing ? "正在保存到待处理…" : recordedAudio ? "录音保存未完成" : "点击开始语音记录"}</p>
      <p className="mt-2 text-xs text-ink-soft">录音仅用于转写，并按后端清理策略删除</p>
    </div> : <div className="flex flex-1 flex-col py-6">
      <h1 className="font-display text-2xl font-extrabold text-ink">发生什么了？</h1>
      <p className="mt-1 text-sm text-ink-soft">写下现场的一个变化，随时可以修改。</p>
      <textarea value={text} onChange={(event) => setText(event.target.value)} rows={8} placeholder="例如：三个孩子站在门口，没有进入共读区域……" className="mt-3 w-full flex-1 resize-none rounded-2xl border-2 border-ink bg-cream p-4 text-sm outline-none focus:border-leaf" />
    </div>}
    {error && <p className="mb-3 mt-3 text-sm font-bold text-red-700">{error}</p>}
    {inputMode === "audio" ? (transcribing || recordedAudio ? <button onClick={() => void uploadRecording()} disabled={recording || transcribing} className="mt-3 w-full rounded-full border-2 border-ink bg-ink px-5 py-3 text-sm font-bold text-cream shadow-[3px_3px_0_0_#1c2b0a] disabled:cursor-not-allowed disabled:border-ink/10 disabled:bg-ink/10 disabled:text-ink-soft">{transcribing ? "正在保存…" : "重新上传这段录音"}</button> : null) : <div className="mt-3 space-y-3">
      <button onClick={startTextReflection} disabled={!text.trim() || submitting} className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a] disabled:cursor-not-allowed disabled:border-ink/10 disabled:bg-ink/10 disabled:text-ink-soft">{submitting ? "正在开始…" : "开始 AI 复盘"}</button>
      <button onClick={saveTextForLater} disabled={!text.trim() || submitting} className="w-full rounded-full border-2 border-ink/40 bg-cream px-5 py-3 text-sm font-bold text-ink-soft disabled:cursor-not-allowed disabled:opacity-50">稍后再说</button>
    </div>}
  </section>;
}
