import { useEffect, useMemo, useRef, useState } from "react";
import { confirmExperience, createAudioCapture, createTextCapture, getCaptureSession, listExperiences, listPendingSessions, patchCaptureSession, patchDraft, patchReflectionAnswer, requestDecisionSupport, requestDecisionSupportAudio, startReflection as requestReflection, submitAudioTurn, submitTextTurn, type CaptureSessionSummary } from "@/api/capture";
import type { CaptureSession, DecisionSupportResponse, ExperienceContent, ExperienceResponse } from "@/api/types";
import { RequestError } from "@/api/client";
import mic from "@/imports/capture-mic.svg";
import mascot from "@/imports/image-2.png";
import success from "@/imports/success-icon.svg";
import backArrow from "@/imports/back-arrow.svg";
import navMic from "@/imports/capture-nav-mic.svg";
import navMicInactive from "@/imports/capture-nav-mic-inactive.svg";
import navTheme from "@/imports/capture-nav-theme.svg";
import navThemeActive from "@/imports/capture-nav-theme-active.svg";
import navMine from "@/imports/capture-nav-mine.svg";
import navMineActive from "@/imports/capture-nav-mine-active.svg";
import kids from "@/imports/themes-kids.svg";
import volunteer from "@/imports/themes-volunteer.svg";
import reading from "@/imports/themes-reading.svg";
import community from "@/imports/themes-community.svg";

type ThemeId = "kids" | "volunteer" | "reading" | "community";
type Screen = "capture" | "pending" | "reflection" | "card" | "success" | "mine" | "themes" | "theme" | "detail";
type Card = { id: string; themeId: ThemeId; title: string; date: string; fields: string[]; demo?: boolean };
type ReflectionTurn = { question: string; questionTurnId?: string; answer?: string; answerTurnId?: string };

const labels = ["发生了什么", "我做了什么调整", "观察到的结果", "似乎有效", "反思与局限", "注意事项 / 适用条件", "还不确定"];
const themes: Array<{ id: ThemeId; name: string; desc: string; icon: string }> = [
  { id: "kids", name: "儿童活动引导", desc: "现场注意力、情绪与秩序", icon: kids },
  { id: "volunteer", name: "志愿者协作", desc: "分工、沟通与现场配合", icon: volunteer },
  { id: "reading", name: "阅读推广", desc: "选书、共读与参与度", icon: reading },
  { id: "community", name: "社区活动运营", desc: "报名、动员与现场组织", icon: community },
];
const initialCards: Card[] = [
  { id: "k1", themeId: "kids", title: "先让孩子自由选书，再邀请进入共读", date: "2026 / 08 / 28", fields: ["活动开始时，三个孩子停在门口，没有进入共读区域。", "把围坐讲故事调整为先自由选书，再邀请他们分享。", "三个孩子随后陆续参与，有人先看绘本后主动提问。", "先给低门槛的自主选择，可能更容易进入活动。", "只观察到一次，不能证明适用于所有孩子。", "孩子明显紧张或人数较多时，可先减少集体压力。", "下次需要观察自由选书会不会挤占共读时间。"] },
  { id: "k2", themeId: "kids", title: "用明确的小任务承接排队等待", date: "2026 / 08 / 25", fields: ["排队环节有孩子开始追跑、走神。", "把等待改成“帮我找三本绿色封面的书”的小任务。", "追跑减少，孩子开始互相展示找到的书。", "具体且能完成的小任务可能降低无聊感。", "人数多时任务可能反而制造拥挤。", "任务难度要与年龄和空间匹配。", "需要继续比较不同任务的效果。"] },
  { id: "v1", themeId: "volunteer", title: "活动前用三分钟说清分工，现场少了重复询问", date: "2026 / 08 / 20", fields: ["活动开始后志愿者反复确认谁负责签到、谁陪读。", "开场前把每个人的第一职责和求助对象写在小卡片上。", "签到和陪读衔接更顺，临时问题能找到对应的人。", "短而具体的分工说明似乎比临场口头分配稳定。", "人员临时缺席时卡片需要马上更新。", "分工只写第一责任，不把现场判断变成死流程。", "是否适用于更大规模团队仍待验证。"], demo: true },
  { id: "v2", themeId: "volunteer", title: "用一句同步替代长串群消息", date: "2026 / 08 / 18", fields: ["现场变更被埋在群聊中，部分成员没有看到。", "用“发生什么—谁处理—何时确认”三句式发布变更。", "需要行动的人更快回复，重复追问减少。", "格式稳定有助于快速识别关键信息。", "紧急情况仍需要电话或当面确认。", "不要把复杂背景全部塞进一条提醒。", "需要观察是否会增加信息模板负担。"], demo: true },
  { id: "r1", themeId: "reading", title: "先用封面和一句问题选书，孩子更愿意开口", date: "2026 / 08 / 16", fields: ["共读开始时，多数孩子只翻页、不愿回应提问。", "先展示封面，问“你觉得这本书里谁最着急”，再开始读。", "孩子开始猜测角色和情节，发言人数增加。", "低门槛猜测题可能降低了开口压力。", "熟悉故事的孩子仍可能抢答。", "问题要允许多个答案，避免变成知识测验。", "需比较不同年龄段对封面提问的反应。"], demo: true },
  { id: "r2", themeId: "reading", title: "把共读拆成短段落，给走神的孩子回来的机会", date: "2026 / 08 / 14", fields: ["长段朗读后，部分孩子开始离座。", "每读两页暂停一次，让孩子找一个细节或做一个动作。", "离座次数减少，孩子能重新跟上故事。", "短暂停顿可能让注意力有恢复空间。", "频繁停顿会影响故事连贯性。", "选择确实值得停下的页面，不必机械打断。", "需要记录最合适的段落长度。"], demo: true },
  { id: "c1", themeId: "community", title: "把报名提醒换成具体场景，家长回复更快", date: "2026 / 08 / 12", fields: ["活动报名通知发出后，家长回复较少。", "把通知改成活动画面、明确时段和一句孩子能做什么。", "当日确认人数增加，家长提出的问题更具体。", "具体场景可能帮助家长判断是否适合参与。", "增加图片制作成本，不能每次都依赖。", "报名信息仍需保留地点、时间和联系人。", "是否长期有效还需多次活动比较。"], demo: true },
  { id: "c2", themeId: "community", title: "给第一次来的家庭一个可见的第一步", date: "2026 / 08 / 10", fields: ["第一次到场的家庭停在入口，不知道先做什么。", "入口放置“先选一本书—找志愿者盖章—坐到地垫”的三步提示。", "新家庭更快进入区域，志愿者重复说明减少。", "可见的第一步可能降低陌生环境的不确定感。", "图示对阅读能力较弱的家长仍需更直观。", "提示应放在真正进入活动前的位置。", "还需观察高峰期是否仍有效。"], demo: true },
];

const draftSeed = initialCards[0].fields;

function Button({ children, onClick, variant = "primary", disabled = false }: { children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "dark"; disabled?: boolean }) {
  const style = variant === "primary" ? "bg-lime" : variant === "dark" ? "bg-ink text-cream" : "bg-cream";
  return <button disabled={disabled} onClick={onClick} className={`w-full rounded-full border-2 border-ink px-4 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a] disabled:cursor-not-allowed disabled:border-ink/15 disabled:bg-ink/10 disabled:text-ink-soft ${style}`}>{children}</button>;
}

function Header({ title, onBack, right }: { title: string; onBack?: () => void; right?: string }) {
  return <header className="flex items-center justify-between border-b border-ink/15 px-5 py-4"><span className="flex h-10 w-10 items-center justify-center">{onBack && <button onClick={onBack} className="flex h-10 w-10 items-center justify-center rounded-full border-2 border-ink bg-cream" aria-label="返回"><img src={backArrow} className="h-4 w-4" alt="" /></button>}</span><h1 className="font-display text-xl font-extrabold">{title}</h1><span className="w-10 text-right text-xs font-bold text-leaf">{right}</span></header>;
}

export function DemoFrontend() {
  const [screen, setScreen] = useState<Screen>("capture");
  const [voiceCount, setVoiceCount] = useState(0);
  const [recording, setRecording] = useState(false);
  const [note, setNote] = useState("");
  const [transcript, setTranscript] = useState("活动开始时有三个孩子站在门口大约五分钟，我把围坐讲故事改成了自由选书。");
  const [expanded, setExpanded] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [answers, setAnswers] = useState<string[]>([]);
  const [reflectionTurns, setReflectionTurns] = useState<ReflectionTurn[]>([]);
  const [draft, setDraft] = useState([...draftSeed]);
  const [cards, setCards] = useState<Card[]>(initialCards);
  const [remoteCards, setRemoteCards] = useState<Card[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [pendingSessions, setPendingSessions] = useState<CaptureSessionSummary[]>([]);
  const [showPendingRecords, setShowPendingRecords] = useState(false);
  const [showConfirmedRecords, setShowConfirmedRecords] = useState(false);
  const [sessionRestoring, setSessionRestoring] = useState(false);
  const [selectedTheme, setSelectedTheme] = useState<ThemeId>("kids");
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [detailOrigin, setDetailOrigin] = useState<"mine" | "theme">("mine");
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [concern, setConcern] = useState("");
  const [decisionResult, setDecisionResult] = useState<DecisionSupportResponse | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionMode, setDecisionMode] = useState<"audio" | "text">("audio");
  const [decisionAudio, setDecisionAudio] = useState<Blob | null>(null);
  const [decisionRecording, setDecisionRecording] = useState(false);
  const [decisionSeconds, setDecisionSeconds] = useState(0);
  const [showTranscript, setShowTranscript] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [sourceMode, setSourceMode] = useState<"audio" | "text" | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [reflectionQuestion, setReflectionQuestion] = useState<string | null>(null);
  const [reflectionError, setReflectionError] = useState<string | null>(null);
  const [answerMode, setAnswerMode] = useState<"audio" | "text">("audio");
  const [answerRecording, setAnswerRecording] = useState(false);
  const [answerSeconds, setAnswerSeconds] = useState(0);
  const [recordedAnswerAudio, setRecordedAnswerAudio] = useState<Blob | null>(null);
  const [answerSubmitting, setAnswerSubmitting] = useState(false);
  const [editingAnswerTurnId, setEditingAnswerTurnId] = useState<string | null>(null);
  const [editingAnswerText, setEditingAnswerText] = useState("");
  const [cardSaving, setCardSaving] = useState(false);
  const [cardError, setCardError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const answerRecorderRef = useRef<MediaRecorder | null>(null);
  const answerStreamRef = useRef<MediaStream | null>(null);
  const answerTimerRef = useRef<number | null>(null);
  const decisionRecorderRef = useRef<MediaRecorder | null>(null);
  const decisionStreamRef = useRef<MediaStream | null>(null);
  const decisionTimerRef = useRef<number | null>(null);
  const questions = ["当时最重要的现场变化是什么？", "你具体做了什么调整，为什么这样做？", "调整后观察到了哪些可见变化？"];
  const activeTheme = themes.find((theme) => theme.id === selectedTheme)!;
  const allCards = useMemo(() => {
    const knownIds = new Set(remoteCards.map((card) => card.id));
    return [...remoteCards, ...cards.filter((card) => !knownIds.has(card.id))];
  }, [cards, remoteCards]);
  const themeCards = useMemo(() => allCards.filter((card) => card.themeId === selectedTheme), [allCards, selectedTheme]);
  const myCards = remoteCards.length ? remoteCards : cards;

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (answerTimerRef.current !== null) window.clearInterval(answerTimerRef.current);
    answerStreamRef.current?.getTracks().forEach((track) => track.stop());
    if (decisionTimerRef.current !== null) window.clearInterval(decisionTimerRef.current);
    decisionStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (screen !== "mine") return;
    let cancelled = false;
    async function loadMyRecords() {
      try {
        setRecordsLoading(true); setRecordsError(null);
        const [records, sessions] = await Promise.all([listExperiences(), listPendingSessions()]);
        if (!cancelled) {
          setRemoteCards(records.map(experienceToCard));
          const pending = sessions.filter((item) => item.status !== "confirmed" && item.status !== "failed");
          setPendingSessions(pending);
          setPendingCount(pending.length);
        }
      } catch (reason) {
        if (!cancelled) setRecordsError(reason instanceof RequestError ? reason.message : "暂时无法读取已确认经验。");
      } finally {
        if (!cancelled) setRecordsLoading(false);
      }
    }
    void loadMyRecords();
    return () => { cancelled = true; };
  }, [screen]);

  useEffect(() => {
    const storedSessionId = localStorage.getItem("practice-memory:last-session");
    if (storedSessionId) void restoreSession(storedSessionId, true);
  }, []);

  function formatDuration(seconds: number) {
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function experienceToCard(experience: ExperienceResponse): Card {
    const fields = [experience.context, experience.action_and_reason, experience.observed_result, experience.went_well, experience.shortcomings, experience.things_to_note, experience.open_question].map((value) => value ?? "");
    const title = experience.action_and_reason || experience.context || "一条已确认经验";
    return { id: experience.id, themeId: "kids", title, date: new Date(experience.recorded_at).toLocaleDateString("zh-CN").replaceAll("/", " / "), fields };
  }

  function reflectionTurnsFromSession(detail: CaptureSession): ReflectionTurn[] {
    const turns: ReflectionTurn[] = [];
    detail.conversation.forEach((message, index) => {
      if (message.kind !== "question") return;
      const answer = detail.conversation[index + 1];
      turns.push({
        question: message.text,
        questionTurnId: message.turn_id,
        answer: answer?.kind === "answer" ? answer.text : undefined,
        answerTurnId: answer?.kind === "answer" ? answer.turn_id : undefined,
      });
    });
    return turns;
  }

  function applyReflectionDetail(detail: CaptureSession) {
    const fields = draftToFields(detail.draft);
    if (detail.status === "needs_confirmation" && fields) { setDraft(fields); setScreen("card"); return; }
    const turns = reflectionTurnsFromSession(detail);
    setReflectionTurns(turns);
    setReflectionQuestion(turns.at(-1)?.answer ? null : turns.at(-1)?.question ?? null);
    setScreen("reflection");
  }

  async function restoreSession(id: string, restoreOnLaunch = false) {
    try {
      setSessionRestoring(true); setCaptureError(null);
      const detail = await getCaptureSession(id);
      const storedSourceMode = localStorage.getItem("practice-memory:last-source-mode");
      setSessionId(detail.id); setTranscript(detail.marker_transcript ?? ""); setVoiceCount(1);
      setSourceMode(storedSourceMode === "audio" || storedSourceMode === "text" ? storedSourceMode : "text");
      if (detail.status === "marked") { setScreen("pending"); return; }
      if (detail.status === "reflecting") {
        applyReflectionDetail(detail); return;
      }
      if (detail.status === "needs_confirmation" && detail.draft) {
        const fields = draftToFields(detail.draft);
        if (fields) setDraft(fields);
        setScreen("card"); return;
      }
      if (detail.status === "confirmed") {
        localStorage.removeItem("practice-memory:last-session");
        localStorage.removeItem("practice-memory:last-source-mode");
        if (!restoreOnLaunch) setScreen("mine");
        return;
      }
      setCaptureError("这条记录处理失败，请重新开始记录。");
      localStorage.removeItem("practice-memory:last-session");
      localStorage.removeItem("practice-memory:last-source-mode");
    } catch (reason) {
      setCaptureError(reason instanceof RequestError ? reason.message : "无法恢复上次记录。");
      if (reason instanceof RequestError && reason.status === 404) {
        localStorage.removeItem("practice-memory:last-session");
        localStorage.removeItem("practice-memory:last-source-mode");
      }
      if (!restoreOnLaunch) setScreen("capture");
    } finally { setSessionRestoring(false); }
  }

  async function openLatestPending() {
    try {
      const sessions = await listPendingSessions();
      const latest = sessions.find((item) => item.status !== "confirmed" && item.status !== "failed");
      const pending = sessions.filter((item) => item.status !== "confirmed" && item.status !== "failed");
      setPendingSessions(pending); setPendingCount(pending.length);
      if (latest) await restoreSession(latest.id); else setScreen("capture");
    } catch (reason) {
      setRecordsError(reason instanceof RequestError ? reason.message : "暂时无法读取待处理记录。");
    }
  }

  function releaseMicrophone() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  async function startBrowserRecording() {
    setCaptureError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setCaptureError("当前浏览器不支持录音，请改用文字输入。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
      recorder.onstop = () => {
        setRecordedAudio(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        setSourceMode("audio");
        setVoiceCount(1);
        setRecording(false);
        if (timerRef.current !== null) window.clearInterval(timerRef.current);
        timerRef.current = null;
        releaseMicrophone();
      };
      recorderRef.current = recorder;
      streamRef.current = stream;
      setRecordingSeconds(0);
      recorder.start();
      setRecording(true);
      timerRef.current = window.setInterval(() => setRecordingSeconds((seconds) => seconds + 1), 1000);
    } catch {
      setCaptureError("未获得麦克风权限。请允许麦克风权限后重试，或改用文字输入。");
      releaseMicrophone();
    }
  }

  function stopBrowserRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function waitForTranscript(id: string) {
    for (let attempt = 0; attempt < 15; attempt += 1) {
      const detail = await getCaptureSession(id);
      if (detail.marker_transcript || detail.status === "failed") return detail;
      await new Promise((resolve) => window.setTimeout(resolve, 800));
    }
    return getCaptureSession(id);
  }

  async function completeCapture() {
    if (recording || uploading || transcribing) return;
    setCaptureError(null);
    if (recordedAudio && note.trim()) {
      setCaptureError("本次 Demo 暂支持一段语音或一段文字其一；请清空文字补充后提交语音，或改用文字记录。");
      return;
    }
    if (!recordedAudio && !note.trim()) return;
    try {
      setUploading(true);
      const created = recordedAudio
        ? await createAudioCapture(recordedAudio, "亲子共读活动")
        : await createTextCapture(note.trim(), "亲子共读活动");
      setSessionId(created.id);
      localStorage.setItem("practice-memory:last-session", created.id);
      localStorage.setItem("practice-memory:last-source-mode", recordedAudio ? "audio" : "text");
      setSourceMode(recordedAudio ? "audio" : "text");
      setScreen("pending");
      if (recordedAudio) {
        setTranscribing(true);
        const detail = await waitForTranscript(created.id);
        if (detail.status === "failed" || !detail.marker_transcript) {
          setCaptureError("语音已上传，但转写暂未完成。请稍后重试或改用文字记录。");
          return;
        }
        setTranscript(detail.marker_transcript);
      } else {
        setTranscript(note.trim());
      }
    } catch (reason) {
      setCaptureError(reason instanceof RequestError ? reason.message : "创建记录失败，请重试。");
      setScreen("capture");
    } finally {
      setUploading(false);
      setTranscribing(false);
    }
  }

  async function saveTranscript() {
    if (!sessionId) return;
    setCaptureError(null);
    try {
      await patchCaptureSession(sessionId, transcript.trim());
      setShowTranscript(false);
    } catch (reason) {
      setCaptureError(reason instanceof RequestError ? reason.message : "保存转写失败，请重试。");
    }
  }
  function draftToFields(value: ExperienceContent | null | undefined) {
    if (!value) return null;
    return [value.context, value.action_and_reason, value.observed_result, value.went_well, value.shortcomings, value.things_to_note, value.open_question].map((item) => item ?? "");
  }

  async function startReflection() {
    setQuestionIndex(0); setAnswers([]); setReflectionTurns([]); setAnswer(""); setRecordedAnswerAudio(null); setReflectionError(null);
    if (!sessionId) { setReflectionTurns([{ question: questions[0] }]); setScreen("reflection"); return; }
    try {
      const current = await getCaptureSession(sessionId);
      if (current.status === "reflecting" || current.status === "needs_confirmation") {
        applyReflectionDetail(current);
        return;
      }
      const result = await requestReflection(sessionId);
      const fields = draftToFields(result.draft as ExperienceContent | null);
      if (fields) { setDraft(fields); setScreen("card"); return; }
      setReflectionQuestion(result.next_question?.text ?? null);
      setReflectionTurns(result.next_question?.text ? [{ question: result.next_question.text }] : []);
      setScreen("reflection");
    } catch (reason) {
      setReflectionError(reason instanceof RequestError ? reason.message : "AI 复盘启动失败，请重试。");
    }
  }

  async function submitAnswer() {
    if (!answer.trim() || answerSubmitting) return;
    setReflectionError(null);
    if (!sessionId) {
      const sent = answer.trim();
      setAnswers((items) => [...items, sent]);
      setReflectionTurns((turns) => turns.map((turn, index) => index === turns.length - 1 ? { ...turn, answer: sent } : turn));
      setAnswer("");
      if (questionIndex === questions.length - 1) setScreen("card"); else {
        setQuestionIndex((index) => index + 1);
        setReflectionTurns((turns) => [...turns, { question: questions[questionIndex + 1] }]);
      }
      return;
    }
    try {
      setAnswerSubmitting(true);
      const sent = answer.trim();
      const result = await submitTextTurn(sessionId, sent);
      setAnswers((items) => [...items, result.answer_transcript || sent]); setAnswer("");
      const fields = draftToFields(result.draft as ExperienceContent | null);
      if (fields) { setDraft(fields); setScreen("card"); return; }
      applyReflectionDetail(await getCaptureSession(sessionId));
    } catch (reason) {
      setReflectionError(reason instanceof RequestError ? reason.message : "提交回答失败，请重试。");
    } finally { setAnswerSubmitting(false); }
  }

  async function startAnswerRecording() {
    setReflectionError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setReflectionError("当前浏览器不支持录音，请改用文字回答。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
      recorder.onstop = () => {
        setRecordedAnswerAudio(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        setAnswerRecording(false);
        if (answerTimerRef.current !== null) window.clearInterval(answerTimerRef.current);
        answerTimerRef.current = null;
        answerStreamRef.current?.getTracks().forEach((track) => track.stop());
        answerStreamRef.current = null;
      };
      answerRecorderRef.current = recorder;
      answerStreamRef.current = stream;
      setAnswerSeconds(0); setRecordedAnswerAudio(null); setAnswerRecording(true);
      recorder.start();
      answerTimerRef.current = window.setInterval(() => setAnswerSeconds((seconds) => seconds + 1), 1000);
    } catch {
      setReflectionError("未获得麦克风权限。请允许权限后重试，或改用文字回答。");
    }
  }

  function stopAnswerRecording() {
    if (answerRecorderRef.current?.state === "recording") answerRecorderRef.current.stop();
  }

  async function submitAnswerAudio() {
    if (!recordedAnswerAudio || answerSubmitting) return;
    if (!sessionId) {
      const sent = `语音回答已记录（${formatDuration(Math.max(1, answerSeconds))}）`;
      setAnswers((items) => [...items, sent]);
      setReflectionTurns((turns) => turns.map((turn, index) => index === turns.length - 1 ? { ...turn, answer: sent } : turn));
      setRecordedAnswerAudio(null);
      if (questionIndex === questions.length - 1) setScreen("card"); else {
        setQuestionIndex((index) => index + 1);
        setReflectionTurns((turns) => [...turns, { question: questions[questionIndex + 1] }]);
      }
      return;
    }
    try {
      setAnswerSubmitting(true); setReflectionError(null);
      const result = await submitAudioTurn(sessionId, recordedAnswerAudio);
      const sent = result.answer_transcript || `语音回答（${formatDuration(Math.max(1, answerSeconds))}）`;
      setAnswers((items) => [...items, sent]);
      setRecordedAnswerAudio(null);
      const fields = draftToFields(result.draft as ExperienceContent | null);
      if (fields) { setDraft(fields); setScreen("card"); return; }
      applyReflectionDetail(await getCaptureSession(sessionId));
    } catch (reason) {
      setReflectionError(reason instanceof RequestError ? reason.message : "语音回答提交失败，请重试。");
    } finally { setAnswerSubmitting(false); }
  }

  async function saveEditedAnswer(turnId: string) {
    if (!sessionId || !editingAnswerText.trim() || answerSubmitting) return;
    try {
      setAnswerSubmitting(true); setReflectionError(null);
      const result = await patchReflectionAnswer(sessionId, turnId, editingAnswerText.trim());
      setEditingAnswerTurnId(null); setEditingAnswerText("");
      const fields = draftToFields(result.draft as ExperienceContent | null);
      if (fields) { setDraft(fields); setScreen("card"); return; }
      applyReflectionDetail(await getCaptureSession(sessionId));
    } catch (reason) {
      setReflectionError(reason instanceof RequestError ? reason.message : "修改回答失败，请重试。");
    } finally { setAnswerSubmitting(false); }
  }
  async function saveCard() {
    if (cardSaving) return;
    setCardError(null);
    const newCard: Card = { id: `new-${Date.now()}`, themeId: "kids", title: "先让孩子自由选书，再邀请进入共读", date: "2026 / 08 / 30", fields: draft };
    if (!sessionId) {
      setCards((current) => [newCard, ...current]); setSelectedCard(newCard); setScreen("success"); return;
    }
    try {
      setCardSaving(true);
      await patchDraft(sessionId, {
        context: draft[0], action_and_reason: draft[1], observed_result: draft[2], went_well: draft[3],
        shortcomings: draft[4], things_to_note: draft[5], open_question: draft[6],
      });
      await confirmExperience(sessionId);
      localStorage.removeItem("practice-memory:last-session");
      localStorage.removeItem("practice-memory:last-source-mode");
      setCards((current) => [newCard, ...current]);
      setSelectedCard(newCard);
      setScreen("success");
    } catch (reason) {
      setCardError(reason instanceof RequestError ? reason.message : "保存经验卡片失败，请检查后端服务后重试。");
    } finally { setCardSaving(false); }
  }

  async function leaveCardToMine() {
    if (!sessionId) { setScreen("mine"); return; }
    try {
      setCardSaving(true); setCardError(null);
      await patchDraft(sessionId, {
        context: draft[0], action_and_reason: draft[1], observed_result: draft[2], went_well: draft[3],
        shortcomings: draft[4], things_to_note: draft[5], open_question: draft[6],
      });
      setScreen("mine");
    } catch (reason) {
      setCardError(reason instanceof RequestError ? reason.message : "暂时无法保存卡片草稿，请重试。");
    } finally { setCardSaving(false); }
  }

  async function startDecisionRecording() {
    setDecisionError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setDecisionError("当前浏览器不支持录音，请改用文字提问。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
      recorder.onstop = () => {
        setDecisionAudio(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        setDecisionRecording(false);
        if (decisionTimerRef.current !== null) window.clearInterval(decisionTimerRef.current);
        decisionTimerRef.current = null;
        decisionStreamRef.current?.getTracks().forEach((track) => track.stop());
        decisionStreamRef.current = null;
      };
      decisionRecorderRef.current = recorder;
      decisionStreamRef.current = stream;
      setDecisionSeconds(0); setDecisionAudio(null); setDecisionRecording(true);
      recorder.start();
      decisionTimerRef.current = window.setInterval(() => setDecisionSeconds((seconds) => seconds + 1), 1000);
    } catch {
      setDecisionError("未获得麦克风权限。请允许权限后重试，或改用文字提问。");
    }
  }

  function stopDecisionRecording() {
    if (decisionRecorderRef.current?.state === "recording") decisionRecorderRef.current.stop();
  }

  function closeDecisionSheet() {
    if (decisionRecorderRef.current?.state === "recording") decisionRecorderRef.current.stop();
    setDecisionOpen(false);
  }

  async function runDecisionSupport() {
    if (decisionLoading) return;
    const useAudio = decisionMode === "audio";
    if (useAudio ? !decisionAudio : !concern.trim()) return;
    try {
      setDecisionLoading(true); setDecisionError(null); setDecisionResult(null);
      const result = useAudio
        ? await requestDecisionSupportAudio(decisionAudio!)
        : await requestDecisionSupport(concern.trim());
      setDecisionResult(result);
    } catch (reason) {
      setDecisionError(reason instanceof RequestError ? reason.message : "暂时无法查找相似经验，请稍后重试。");
    } finally { setDecisionLoading(false); }
  }

  const content = (() => {
    if (screen === "capture") return <section className="flex min-h-full flex-col px-5 pb-6 pt-3">
      <button onClick={() => setExpanded((open) => !open)} className="flex items-center gap-3 rounded-2xl border-2 border-ink bg-cream px-4 py-3 text-left shadow-[2px_2px_0_0_#1c2b0a]"><span>🎧</span><span className="flex-1"><b className="block">语音归纳</b><small className="text-ink-soft">已录制 {voiceCount} 条语音</small></span><span>{expanded ? "⌃" : "⌄"}</span></button>
      {expanded && <div className="mt-2 rounded-2xl border-2 border-ink/15 bg-cream p-3 text-sm">{voiceCount ? Array.from({ length: voiceCount }, (_, i) => <p key={i} className="flex justify-between py-1"><span>🎙 语音 {i + 1}</span><span className="text-ink-soft">00:0{i + 1}</span></p>) : <p className="text-ink-soft">还没有录音，点击麦克风开始记录。</p>}</div>}
      <div className="flex flex-1 flex-col items-center justify-center py-8 text-center"><button onClick={() => recording ? stopBrowserRecording() : startBrowserRecording()} className="relative h-52 w-52" aria-label={recording ? "停止录音" : "开始录音"}>{recording && <><span className="animate-ring absolute inset-0 rounded-full bg-lime/70" /><span className="animate-ring absolute inset-0 rounded-full bg-lime/70" style={{ animationDelay: "1s" }} /></>}<img src={mic} className="relative h-full w-full" alt="麦克风" /></button><h2 className="mt-6 font-display text-xl font-extrabold">{recording ? formatDuration(recordingSeconds) : recordedAudio ? `本段语音已录制 · ${formatDuration(Math.max(1, recordingSeconds))}` : voiceCount ? "点击继续补充一段" : "点击开始语音记录"}</h2><p className="mt-2 text-xs text-ink-soft">录音内容默认仅自己可见</p>{recordedAudio && <button onClick={() => { setRecordedAudio(null); setVoiceCount(0); setRecordingSeconds(0); }} className="mt-3 text-xs font-bold text-leaf underline">重新录制本段</button>}</div>
      <textarea disabled={Boolean(recordedAudio)} value={note} onChange={(event) => { setNote(event.target.value); if (event.target.value.trim()) setSourceMode("text"); }} placeholder={recordedAudio ? "本次语音已录制；Demo 不支持同时追加文字" : "改用文字记录"} rows={2} className="mb-4 w-full resize-none rounded-2xl border-2 border-ink/35 bg-cream p-3 text-sm outline-none disabled:cursor-not-allowed disabled:opacity-50" />
      {captureError && <p className="mb-3 text-sm font-bold text-red-700">{captureError}</p>}
      <Button variant="dark" disabled={(!recordedAudio && !note.trim()) || recording || uploading || transcribing} onClick={completeCapture}>{uploading ? "正在上传…" : transcribing ? "正在转写…" : "活动完成，去整理"}</Button>
    </section>;

    if (screen === "pending") return <section className="flex min-h-full flex-col"><Header title="待整理" right="待整理" onBack={() => setScreen("capture")} /><div className="flex-1 space-y-5 px-5 py-4">{transcribing && <div className="rounded-2xl border-2 border-ink bg-lime-wash p-4 text-sm font-bold">正在将语音转成文字…</div>}<div className="rounded-2xl border-2 border-ink bg-lime-wash p-4 shadow-[3px_3px_0_0_#1c2b0a]"><b className="text-xs text-leaf">文字内容</b><p className="mt-2 text-sm">{sourceMode === "text" ? transcript : note || "暂无文字补充"}</p></div>{sourceMode !== "text" && <div><h2 className="mb-2 text-sm font-bold">语音记录</h2><div className="mb-2 rounded-2xl border-2 border-ink/15 bg-cream p-3"><div className="flex items-center gap-2"><span>〽</span><b className="flex-1 text-sm">语音记录 1</b><span className="text-xs text-ink-soft">{formatDuration(Math.max(1, recordingSeconds))}</span><button title="查看转写" onClick={() => setShowTranscript((open) => !open)}>🎙</button></div>{showTranscript && <><textarea value={transcript} onChange={(event) => setTranscript(event.target.value)} rows={4} className="mt-3 w-full resize-none rounded-xl border-2 border-ink bg-lime-wash p-3 text-sm outline-none" /><button onClick={saveTranscript} className="mt-2 rounded-full border border-ink bg-cream px-3 py-1 text-xs font-bold">保存修改</button></>}</div></div>}{captureError && <p className="text-sm font-bold text-red-700">{captureError}</p>}<p className="rounded-2xl border border-ink/15 p-3 text-xs text-ink-soft">你可以先检查原始内容，确认无误后再交给 AI 进行复盘整理。</p></div><div className="border-t border-ink/15 p-5"><Button disabled={transcribing || !transcript.trim()} onClick={startReflection}>AI 复盘</Button></div></section>;

    if (screen === "reflection") return <section className="flex min-h-full flex-col"><Header title="AI 复盘" onBack={() => setScreen("pending")} /><div className="flex-1 space-y-4 px-5 py-4"><div className="rounded-2xl border-2 border-ink/15 bg-lime-wash p-3 text-xs"><b>原始记录 · {voiceCount || 1} 段语音</b><p className="mt-1 line-clamp-2">“{transcript}”</p></div><p className="text-xs font-bold text-ink-soft">🌱 我只问对经验有帮助的问题，一次一个。</p>{reflectionTurns.map((turn, i) => <div key={turn.questionTurnId ?? `${turn.question}-${i}`} className="space-y-2"><div className="max-w-[90%] rounded-2xl rounded-tl-sm border-2 border-ink bg-cream p-3 text-sm"><small className="block text-leaf">AI 问题</small>{turn.question}</div>{turn.answer && <div className="ml-auto max-w-[90%] rounded-2xl rounded-tr-sm border-2 border-ink bg-lime p-3 text-sm"><small className="block text-ink-soft">你的回答</small>{editingAnswerTurnId === turn.answerTurnId ? <><textarea autoFocus value={editingAnswerText} onChange={(event) => setEditingAnswerText(event.target.value)} rows={3} className="mt-2 w-full resize-none rounded-xl border-2 border-ink bg-cream p-2 text-sm text-ink outline-none" /><div className="mt-2 flex gap-2"><button onClick={() => saveEditedAnswer(turn.answerTurnId!)} disabled={answerSubmitting || !editingAnswerText.trim()} className="rounded-full border border-ink bg-cream px-3 py-1 text-xs font-bold disabled:opacity-40">保存并重新追问</button><button onClick={() => { setEditingAnswerTurnId(null); setEditingAnswerText(""); }} className="rounded-full border border-ink/30 px-3 py-1 text-xs">取消</button></div></> : <><p className="mt-1 whitespace-pre-wrap">{turn.answer}</p>{turn.answerTurnId && <button onClick={() => { setEditingAnswerTurnId(turn.answerTurnId!); setEditingAnswerText(turn.answer ?? ""); }} className="mt-2 text-xs font-bold text-ink underline">编辑这条回答</button>}</>}</div>}</div>)}{reflectionError && <p className="text-sm font-bold text-red-700">{reflectionError}</p>}</div><div className="border-t border-ink/15 bg-cream p-5"><div className="mb-3 flex gap-2"><button onClick={() => setAnswerMode("audio")} className={`flex-1 rounded-full border-2 border-ink px-3 py-2 text-xs font-bold ${answerMode === "audio" ? "bg-lime" : "bg-cream"}`}>语音回答</button><button onClick={() => { setAnswerMode("text"); setRecordedAnswerAudio(null); }} className={`flex-1 rounded-full border-2 border-ink px-3 py-2 text-xs font-bold ${answerMode === "text" ? "bg-lime" : "bg-cream"}`}>文字回答</button></div>{answerMode === "audio" ? <><button onClick={() => answerRecording ? stopAnswerRecording() : startAnswerRecording()} disabled={answerSubmitting} className={`mb-3 flex w-full items-center justify-center gap-2 rounded-2xl border-2 border-ink px-4 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a] ${answerRecording ? "bg-ink text-cream" : "bg-lime"}`}>{answerRecording ? `停止录音 · ${formatDuration(answerSeconds)}` : "开始录制语音回答"}</button>{recordedAnswerAudio && <p className="mb-3 rounded-xl bg-lime-wash p-2 text-center text-xs font-bold text-leaf">语音回答已录制，可以提交</p>}<Button onClick={submitAnswerAudio} disabled={!recordedAnswerAudio || answerSubmitting}>{answerSubmitting ? "正在提交…" : "提交语音回答"}</Button></> : <><textarea value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="写下你的回答" rows={3} className="mb-3 w-full resize-none rounded-2xl border-2 border-ink bg-cream p-3 text-sm outline-none" /><Button onClick={submitAnswer} disabled={!answer.trim() || answerSubmitting}>{answerSubmitting ? "正在提交…" : "提交文字回答"}</Button></>}</div></section>;

    if (screen === "card") return <section className="flex min-h-full flex-col"><Header title="经验卡片" onBack={leaveCardToMine} /><div className="flex-1 space-y-4 px-5 py-4"><p className="text-xs font-bold text-leaf">AI 已整理完成 · 请你确认</p><div className="rounded-3xl border-2 border-ink bg-cream p-4 shadow-[4px_4px_0_0_#1c2b0a]"><span className="rounded-full border border-ink bg-lime-wash px-2 py-1 text-xs font-bold">儿童活动引导</span><h2 className="mt-3 font-display text-2xl font-extrabold">先让孩子自由选书，再邀请进入共读</h2>{labels.map((label, i) => <label key={label} className="mt-4 block rounded-2xl bg-lime-wash p-3"><b className="text-sm text-leaf">{label}</b><textarea value={draft[i]} onChange={(event) => setDraft((items) => items.map((item, index) => index === i ? event.target.value : item))} rows={2} className="mt-2 w-full resize-none bg-transparent text-sm outline-none" /></label>)}</div>{cardError && <p className="text-sm font-bold text-red-700">{cardError}</p>}</div><div className="border-t border-ink/15 p-5"><Button disabled={cardSaving} onClick={saveCard}>{cardSaving ? "正在保存…" : "确认保存经验卡片"}</Button></div></section>;

    if (screen === "success") return <section className="flex min-h-full flex-col px-5 py-8 text-center"><img src={success} className="mx-auto mt-12 h-32 w-32" alt="保存成功" /><h1 className="mt-5 font-display text-4xl font-extrabold">已保存！</h1><p className="mt-3 text-sm text-ink-soft">这条经验已进入「我的」，并归入儿童活动引导。</p><div className="mt-8 rounded-2xl border-2 border-ink bg-cream p-4 text-left shadow-[3px_3px_0_0_#1c2b0a]"><small className="font-bold text-leaf">儿童活动引导</small><b className="mt-2 block">先让孩子自由选书，再邀请进入共读</b></div><div className="mt-8 space-y-4"><Button onClick={() => setScreen("mine")}>去我的看看</Button><Button variant="secondary" onClick={() => { setSelectedTheme("kids"); setScreen("theme"); }}>去主题库发现更多经验</Button></div></section>;

    if (screen === "mine") return <section className="space-y-5 px-5 py-4"><div className="rounded-3xl border-2 border-ink bg-lime p-4 shadow-[4px_4px_0_0_#1c2b0a]"><b className="font-display text-2xl">当前演示贡献者</b><p className="mt-1 text-xs">儿童阅读活动 · 一线实践者</p></div><div className="grid grid-cols-2 gap-3"><button onClick={() => setShowPendingRecords((open) => !open)} className="rounded-2xl border-2 border-ink bg-lime-wash p-4 text-left"><b className="block text-2xl text-leaf">{pendingCount}</b><small>待处理 · 点击查看</small></button><button onClick={() => setShowConfirmedRecords((open) => !open)} className="rounded-2xl border-2 border-ink bg-cream p-4 text-left"><b className="block text-2xl text-leaf">{myCards.length}</b><small>已整理 · 点击查看</small></button></div>{showPendingRecords && <div className="space-y-3 rounded-3xl border-2 border-ink bg-lime-wash p-4"><div className="flex items-center justify-between"><h2 className="font-display text-lg font-extrabold">待处理记录</h2><button onClick={openLatestPending} className="text-xs font-bold underline">继续最新一条</button></div>{pendingSessions.length ? pendingSessions.map((item) => <button key={item.id} onClick={() => restoreSession(item.id)} className="w-full rounded-2xl border-2 border-ink bg-cream p-3 text-left shadow-[2px_2px_0_0_#1c2b0a]"><small className="font-bold text-leaf">{item.status === "marked" ? "待整理" : item.status === "reflecting" ? "正在 AI 复盘" : "待确认经验卡"}</small><p className="mt-1 line-clamp-2 text-sm">{item.marker_transcript_preview || "尚未得到可用文字记录"}</p></button>) : <p className="text-sm text-ink-soft">当前没有待处理记录。</p>}</div>}{showConfirmedRecords && <div className="space-y-3 rounded-3xl border-2 border-ink bg-cream p-4"><h2 className="font-display text-lg font-extrabold">已整理经验</h2>{myCards.map((card) => <button key={card.id} onClick={() => { setSelectedCard(card); setDetailOrigin("mine"); setScreen("detail"); }} className="w-full rounded-2xl border-2 border-ink bg-lime-wash p-3 text-left"><small className="text-leaf">{card.date}</small><b className="mt-1 block text-sm">{card.title}</b></button>)}</div>}<h2 className="font-display text-xl font-extrabold">最近留下的经验</h2>{recordsLoading && <p className="text-sm font-bold text-leaf">正在读取经验库…</p>}{recordsError && <p className="text-sm font-bold text-red-700">{recordsError}</p>}{!recordsLoading && myCards.slice(0, 5).map((card) => <button key={card.id} onClick={() => { setSelectedCard(card); setDetailOrigin("mine"); setScreen("detail"); }} className="w-full rounded-2xl border-2 border-ink bg-cream p-4 text-left shadow-[3px_3px_0_0_#1c2b0a]"><small className="text-leaf">{themes.find((theme) => theme.id === card.themeId)?.name} · {card.date}</small><b className="mt-2 block">{card.title}</b></button>)}</section>;

    if (screen === "themes") return <section className="space-y-5 px-5 py-4"><div className="relative overflow-hidden rounded-3xl border-2 border-ink bg-lime p-5 shadow-[4px_4px_0_0_#1c2b0a]"><img src={mascot} className="absolute -right-5 bottom-0 w-40" alt="吉祥物" /><div className="relative max-w-[62%]"><small className="rounded-full border border-ink bg-cream px-2 py-1 font-bold">语音优先</small><h1 className="mt-3 font-display text-3xl font-extrabold">把现场判断<br />留下来</h1><p className="mt-2 text-xs">一句几秒的记录，变成可复用的实践经验。</p></div></div><h2 className="font-display text-xl font-extrabold">正在生长的主题</h2>{themes.map((theme) => <button key={theme.id} onClick={() => { setSelectedTheme(theme.id); setScreen("theme"); }} className="flex w-full items-center gap-3 rounded-2xl border-2 border-ink bg-cream p-4 text-left shadow-[3px_3px_0_0_#1c2b0a]"><img src={theme.icon} className="h-11 w-11 rounded-xl border border-ink bg-lime-wash p-1" alt="" /><span className="flex-1"><b className="block">{theme.name}</b><small className="text-ink-soft">{theme.desc}</small></span><b className="text-leaf">{allCards.filter((card) => card.themeId === theme.id).length}<small className="ml-1 font-normal text-ink-soft">条</small></b></button>)}</section>;

    if (screen === "theme") return <section className="px-5 pb-6"><Header title={activeTheme.name} onBack={() => setScreen("themes")} /><div className="mt-4 rounded-3xl border-2 border-ink bg-lime p-5 shadow-[4px_4px_0_0_#1c2b0a]"><img src={activeTheme.icon} className="h-12 w-12" alt="" /><h2 className="mt-2 font-display text-2xl font-extrabold">{activeTheme.name}</h2><p className="mt-1 text-sm">{activeTheme.desc}</p><p className="mt-3 text-xs text-ink-soft">主题经验来自具体实践，不自动升级为最佳做法。</p></div><div className="mt-5 space-y-3">{themeCards.map((card) => <button key={card.id} onClick={() => { setSelectedCard(card); setDetailOrigin("theme"); setScreen("detail"); }} className="w-full rounded-2xl border-2 border-ink bg-cream p-4 text-left shadow-[3px_3px_0_0_#1c2b0a]"><small className="text-leaf">{card.date}{card.demo ? " · 演示经验" : ""}</small><b className="mt-2 block">{card.title}</b><p className="mt-2 line-clamp-2 text-sm text-ink-soft">{card.fields[0]}</p></button>)}</div><button onClick={() => setDecisionOpen(true)} className="mt-5 w-full rounded-2xl border-2 border-dashed border-leaf bg-lime-wash p-4 text-left text-sm font-bold">带着这个主题去问「决策支持」 →</button></section>;

    return <section className="px-5 pb-6"><Header title="经验卡片" onBack={() => setScreen(detailOrigin)} />{selectedCard && <div className="mt-4 rounded-3xl border-2 border-ink bg-cream p-4 shadow-[4px_4px_0_0_#1c2b0a]"><small className="font-bold text-leaf">{themes.find((theme) => theme.id === selectedCard.themeId)?.name} · {selectedCard.date}</small><h2 className="mt-3 font-display text-2xl font-extrabold">{selectedCard.title}</h2>{labels.map((label, i) => <div key={label} className="mt-4 rounded-2xl bg-lime-wash p-3"><b className="text-sm text-leaf">{label}</b><p className="mt-2 text-sm leading-6">{selectedCard.fields[i]}</p></div>)}<p className="mt-4 rounded-xl border border-ink/15 p-3 text-xs text-ink-soft">经验来源：由一线实践者记录并确认；单次经验，不代表普遍规律。</p></div>}</section>;
  })();

  const navItem = (label: string, active: boolean, activeIcon: string, inactiveIcon: string, onClick: () => void) => <button onClick={onClick} className={`flex min-w-16 flex-col items-center text-xs font-bold ${active ? "text-ink" : "text-ink-soft"}`}><span className={`mb-1 flex h-12 w-12 items-center justify-center rounded-2xl ${active ? "border-2 border-ink bg-lime shadow-[2px_2px_0_0_#1c2b0a]" : ""}`}><img src={active ? activeIcon : inactiveIcon} className="h-7 w-7" alt="" /></span>{label}</button>;
  const nav = <nav className="z-20 flex shrink-0 justify-around border-t-2 border-ink bg-cream px-5 py-2">{navItem("记一下", screen === "capture", navMic, navMicInactive, () => setScreen("capture"))}{navItem("主题库", screen === "themes" || screen === "theme", navThemeActive, navTheme, () => setScreen("themes"))}{navItem("我的", screen === "mine", navMineActive, navMine, () => setScreen("mine"))}</nav>;
  const showNav = ["capture", "mine", "themes", "theme", "detail"].includes(screen);
  const showDecisionFab = screen === "themes" || screen === "theme";
  const decisionSubmitDisabled = decisionLoading || (decisionMode === "audio" ? !decisionAudio : !concern.trim());
  return <div className="flex h-screen w-full justify-center bg-lime-wash/40 sm:items-center sm:p-4"><div className="relative flex h-full w-full max-w-[440px] flex-col overflow-hidden bg-cream shadow-2xl sm:h-[min(900px,calc(100vh-2rem))] sm:rounded-[2.5rem] sm:border-2 sm:border-ink"><div className="flex shrink-0 justify-between px-6 py-3 text-xs font-bold text-ink/65"><span>9:41</span><span>◫ ◫ ◫</span></div><main className="flex-1 overflow-y-auto">{content}</main>{showDecisionFab && !decisionOpen && <button onClick={() => setDecisionOpen(true)} className="absolute bottom-24 right-5 z-30 rounded-2xl border-2 border-ink bg-lime px-3 py-2 text-xs font-bold shadow-[3px_3px_0_0_#1c2b0a]">决策<br />支持</button>}{showNav && nav}{decisionOpen && <div className="absolute inset-0 z-40 flex items-end bg-ink/40" onClick={closeDecisionSheet}><section className="max-h-[90%] w-full overflow-y-auto rounded-t-3xl border-t-2 border-ink bg-cream p-5" onClick={(event) => event.stopPropagation()}><div className="mx-auto h-1.5 w-12 rounded-full bg-ink/25" /><h2 className="mt-4 font-display text-2xl font-extrabold">决策支持</h2><p className="mt-2 text-sm text-ink-soft">描述你此刻拿不准的现场情况，我会带回相关经验供你参考。</p><div className="mt-4 flex gap-2"><button onClick={() => { if (!decisionLoading) setDecisionMode("audio"); }} disabled={decisionLoading} className={`flex-1 rounded-full border-2 border-ink px-3 py-2 text-xs font-bold disabled:opacity-40 ${decisionMode === "audio" ? "bg-lime" : "bg-cream"}`}>语音提问</button><button onClick={() => { if (decisionLoading) return; if (decisionRecorderRef.current?.state === "recording") decisionRecorderRef.current.stop(); setDecisionAudio(null); setDecisionMode("text"); }} disabled={decisionLoading} className={`flex-1 rounded-full border-2 border-ink px-3 py-2 text-xs font-bold disabled:opacity-40 ${decisionMode === "text" ? "bg-lime" : "bg-cream"}`}>文字提问</button></div>{decisionMode === "audio" ? <div className="mt-4 space-y-3"><button onClick={() => decisionRecording ? stopDecisionRecording() : startDecisionRecording()} disabled={decisionLoading} className={`flex w-full items-center justify-center gap-2 rounded-2xl border-2 border-ink px-4 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a] ${decisionRecording ? "bg-ink text-cream" : "bg-lime"}`}>{decisionRecording ? `停止录音 · ${formatDuration(decisionSeconds)}` : decisionAudio ? `重录（当前 ${formatDuration(Math.max(1, decisionSeconds))}）` : "开始录制现场困扰"}</button>{decisionAudio && !decisionRecording && <p className="rounded-xl bg-lime-wash p-2 text-center text-xs font-bold text-leaf">语音已录制，可以提交</p>}</div> : <textarea value={concern} onChange={(event) => { setConcern(event.target.value); setDecisionResult(null); setDecisionError(null); }} placeholder="例如：几个孩子站在门口，我该继续围坐还是先让他们自由选书？" rows={3} className="mt-4 w-full resize-none rounded-2xl border-2 border-ink p-3 text-sm outline-none" />}{decisionLoading && <p className="mt-4 text-sm font-bold text-leaf">正在查找相关经验…</p>}{decisionError && <p className="mt-4 text-sm font-bold text-red-700">{decisionError}</p>}{decisionResult && <div className="mt-4 rounded-2xl border-2 border-ink bg-lime-wash p-3 text-sm">{decisionResult.match ? <><b className="text-leaf">来自过往经验</b><p className="mt-2 font-bold">{decisionResult.match.experience.action_and_reason}</p><p className="mt-2 text-xs text-ink-soft">关联原因：{decisionResult.match.why_similar}</p>{decisionResult.considerations.map((item, index) => <p key={`${item.basis_experience_id}-${index}`} className="mt-3 rounded-xl bg-cream p-2 text-xs"><b>可参考：</b>{item.direction}{item.tradeoff && <><br /><b>需要留意：</b>{item.tradeoff}</>}</p>)}<p className="mt-3 rounded-xl border border-ink/15 bg-cream p-2 text-xs"><b>留给现场的判断：</b>{decisionResult.question_to_consider || "结合现场情况，判断这条经验是否适用。"}</p></> : <><b className="text-leaf">暂未找到足够相似的经验</b><p className="mt-2 text-xs text-ink-soft">可以先按现场情况尝试，并把结果记录下来。</p></>}</div>}<div className="mt-4"><Button disabled={decisionSubmitDisabled} onClick={runDecisionSupport}>{decisionLoading ? "正在查找…" : decisionMode === "audio" ? "用语音查找相似经验" : "查找相似经验"}</Button></div></section></div>}</div></div>;
}
