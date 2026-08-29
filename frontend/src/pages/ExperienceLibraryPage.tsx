import { useEffect, useRef, useState } from "react";
import { listExperiences, requestAudioDecisionSupport, requestDecisionSupport } from "@/api/capture";
import { RequestError } from "@/api/client";
import type { DecisionSupportResponse, ExperienceContent } from "@/api/types";
import { EXPERIENCE_FIELDS } from "@/lib/experience";
import mascot from "@/imports/image-2.png";

type LibraryItem = ExperienceContent & { id: string; recorded_at: string };
const SUMMARY_FIELDS = ["context", "action_and_reason", "observed_result"] as const;

function ExperienceFields({ item, full = false }: { item: ExperienceContent; full?: boolean }) {
  const fields = full ? EXPERIENCE_FIELDS : EXPERIENCE_FIELDS.filter(([key]) => SUMMARY_FIELDS.includes(key as typeof SUMMARY_FIELDS[number]));
  return <div className="mt-3 space-y-2 text-sm">
    {fields.map(([key, label]) => item[key] ? <div key={key}><span className="font-bold text-ink">{label}：</span><span className="text-ink-soft">{item[key]}</span></div> : null)}
  </div>;
}

function compactMatchReason(reason: string) {
  const firstSentence = reason.replace(/concern/g, "当前困扰").replace(/候选/g, "历史经验").split(/[；。]/)[0]?.trim();
  return firstSentence || "这条经验记录了相近的现场情况，可供对照参考。";
}

function ExperienceCard({ item }: { item: ExperienceContent }) {
  return <>
    <ExperienceFields item={item} />
    <details className="mt-3 rounded-xl border border-ink/20 bg-lime-wash/50 p-3 text-sm">
      <summary className="cursor-pointer font-bold text-ink">展开完整经验卡</summary>
      <ExperienceFields item={item} full />
    </details>
  </>;
}

export function ExperienceLibraryPage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [concern, setConcern] = useState("");
  const [supportInputMode, setSupportInputMode] = useState<"text" | "audio">("text");
  const [recording, setRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [result, setResult] = useState<DecisionSupportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    listExperiences().then(setItems).catch(() => setError("暂时无法读取经验库，请稍后重试。")).finally(() => setLoading(false));
  }, []);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function stopMediaStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  async function startSupportRecording() {
    setError(null);
    setRecordedAudio(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("当前浏览器不支持录音，请改用文字描述。");
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
        setRecordedAudio(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        setRecording(false);
        if (timerRef.current !== null) window.clearInterval(timerRef.current);
        timerRef.current = null;
        recorderRef.current = null;
        stopMediaStream();
      };
      streamRef.current = stream;
      recorderRef.current = recorder;
      setRecordingSeconds(0);
      recorder.start();
      setRecording(true);
      timerRef.current = window.setInterval(() => setRecordingSeconds((seconds) => seconds + 1), 1000);
    } catch {
      setError("未获得麦克风权限。请允许麦克风后重试，或改用文字描述。");
      stopMediaStream();
    }
  }

  function stopSupportRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function runSupportRequest(request: () => Promise<DecisionSupportResponse>) {
    setRequesting(true); setError(null); setResult(null);
    try { setResult(await request()); }
    catch (reason) { setError(reason instanceof RequestError ? reason.message : "暂时无法获取经验参考，请重试。"); }
    finally { setRequesting(false); }
  }

  async function requestSupport() {
    if (!concern.trim()) return;
    await runSupportRequest(() => requestDecisionSupport(concern.trim()));
  }

  async function requestAudioSupport() {
    if (!recordedAudio) return;
    if (recordedAudio.size > 15 * 1024 * 1024) {
      setError("录音超过 15 MiB，请缩短后重录。");
      return;
    }
    await runSupportRequest(() => requestAudioDecisionSupport(recordedAudio));
  }

  return <section className="space-y-5 px-5 py-6">
    <div className="relative overflow-hidden rounded-[2rem] border-2 border-ink bg-lime p-5 shadow-[5px_5px_0_0_#1c2b0a]">
      <img src={mascot} alt="经验捕手吉祥物" className="animate-bob pointer-events-none absolute -right-8 bottom-[-24px] w-48 drop-shadow-xl" />
      <div className="relative z-10 max-w-[62%]"><span className="inline-flex rounded-full border-2 border-ink bg-cream px-3 py-1 text-xs font-bold">儿童阅读活动</span><h1 className="mt-3 font-display text-3xl font-extrabold leading-tight text-ink">经验会继续<br />生长</h1><p className="mt-2 text-xs leading-5 text-ink-soft">把经确认的现场记录留下来，在下一次犹豫时带回来参考。</p></div>
    </div>

    <div className="space-y-3 rounded-2xl border-2 border-ink bg-lime-wash p-4">
      <p className="font-bold text-ink">遇到拿不准的现场情况？</p>
      <div className="grid grid-cols-2 gap-2 rounded-xl bg-cream/70 p-1 text-sm font-bold" role="group" aria-label="困扰输入方式">
        <button onClick={() => setSupportInputMode("text")} disabled={recording || requesting} aria-pressed={supportInputMode === "text"} className={`rounded-lg px-3 py-2 disabled:cursor-not-allowed disabled:opacity-50 ${supportInputMode === "text" ? "bg-cream shadow-sm" : "text-ink-soft"}`}>文字描述</button>
        <button onClick={() => setSupportInputMode("audio")} disabled={recording || requesting} aria-pressed={supportInputMode === "audio"} className={`rounded-lg px-3 py-2 disabled:cursor-not-allowed disabled:opacity-50 ${supportInputMode === "audio" ? "bg-cream shadow-sm" : "text-ink-soft"}`}>语音描述</button>
      </div>
      {supportInputMode === "text" ? <>
        <textarea value={concern} onChange={(event) => setConcern(event.target.value)} rows={4} placeholder="例如：孩子站在门口，没有进入共读区域，我该继续围坐还是先让他们自由选书？" className="w-full resize-none rounded-xl border-2 border-ink bg-cream p-3 text-sm outline-none" />
        <button onClick={requestSupport} disabled={!concern.trim() || requesting} className="w-full rounded-full border-2 border-ink bg-lime px-4 py-2 text-sm font-bold disabled:opacity-60">{requesting ? "正在查找经验…" : "查找相似经验"}</button>
      </> : <div className="space-y-3 rounded-xl border-2 border-ink bg-cream p-3">
        <div className="text-center">
          <p className="font-display text-2xl font-extrabold text-ink">{String(Math.floor(recordingSeconds / 60)).padStart(2, "0")}:{String(recordingSeconds % 60).padStart(2, "0")}</p>
          <p className="mt-1 text-xs text-ink-soft">录音只用于本次转写和匹配，不保存为经验</p>
        </div>
        {recording ? <button onClick={stopSupportRecording} className="w-full rounded-full border-2 border-ink bg-red-100 px-4 py-2 text-sm font-bold">停止录音</button> : <button onClick={() => void startSupportRecording()} disabled={requesting} className="w-full rounded-full border-2 border-ink bg-lime px-4 py-2 text-sm font-bold disabled:opacity-60">{recordedAudio ? "重新录制" : "开始录音"}</button>}
        {recordedAudio && !recording && <button onClick={() => void requestAudioSupport()} disabled={requesting} className="w-full rounded-full border-2 border-ink bg-ink px-4 py-2 text-sm font-bold text-cream disabled:opacity-60">{requesting ? "正在转写并查找…" : "用这段语音查找经验"}</button>}
      </div>}
    </div>

    {error && <p className="text-sm font-bold text-red-700">{error}</p>}
    {result && <section className="space-y-3">
      <div className="rounded-2xl border-2 border-ink bg-cream p-4"><p className="text-xs font-bold text-leaf">当前困扰</p><p className="mt-2 text-sm leading-6 text-ink">{result.concern_transcript}</p></div>
      {result.match ? <>
        <article className="rounded-2xl border-2 border-ink bg-cream p-4 shadow-[3px_3px_0_0_#1c2b0a]"><p className="text-xs font-bold text-leaf">来自过往经验 · 已确认</p><p className="mt-2 text-sm leading-6 text-ink">{compactMatchReason(result.match.why_similar)}</p><ExperienceCard item={result.match.experience} /></article>
        {result.considerations.length > 0 && <div className="rounded-2xl border-2 border-ink bg-lime-wash p-4"><p className="text-sm font-bold text-ink">可参考的历史做法</p>{result.considerations.map((item, index) => <div key={`${item.basis_experience_id}-${index}`} className="mt-3 rounded-xl bg-cream p-3 text-sm"><p className="text-ink">{item.direction}</p>{item.tradeoff && <p className="mt-2 text-ink-soft">已记录的限制：{item.tradeoff}</p>}</div>)}</div>}
        {result.question_to_consider && <div className="rounded-2xl border-2 border-dashed border-ink/40 bg-cream p-4 text-sm"><p className="font-bold text-ink">留给现场的判断</p><p className="mt-2 text-ink-soft">{result.question_to_consider}</p></div>}
      </> : <div className="rounded-2xl border-2 border-dashed border-ink/30 bg-cream p-4 text-sm text-ink-soft">暂未找到相似经验。你可以先记录这次实践，之后由团队持续积累可参考的经验。</div>}
    </section>}

    <section className="space-y-3 border-t-2 border-ink/15 pt-5">
      <h2 className="font-display text-2xl font-extrabold text-ink">已确认经验</h2>
      {loading ? <p className="text-sm text-ink-soft">正在读取经验库…</p> : items.length === 0 ? <div className="rounded-2xl border-2 border-dashed border-ink/25 bg-cream p-5 text-sm text-ink-soft">还没有已确认经验。</div> : items.map((item) => <article key={item.id} className="rounded-2xl border-2 border-ink bg-cream p-4 text-sm shadow-[3px_3px_0_0_#1c2b0a]"><p className="text-xs font-bold text-leaf">已确认经验</p><b className="mt-2 block">{item.context ?? "一条儿童阅读活动经验"}</b><ExperienceCard item={item} /></article>)}
    </section>
  </section>;
}
