import { useEffect, useState } from "react";
import { listExperiences, listPendingSessions } from "@/api/capture";
import type { CaptureSessionSummary } from "@/api/capture";
import type { ExperienceContent } from "@/api/types";
import avatar from "@/imports/mine-avatar.png";

const STATUS_LABEL: Record<CaptureSessionSummary["status"], string> = {
  marked: "待开始复盘",
  reflecting: "正在复盘",
  needs_confirmation: "待确认经验卡",
  confirmed: "已确认",
  failed: "处理失败",
};

const STATUS_ACTION: Record<CaptureSessionSummary["status"], string> = {
  marked: "开始 AI 复盘",
  reflecting: "继续回答 AI 问题",
  needs_confirmation: "查看并确认经验卡",
  confirmed: "已确认",
  failed: "请重新记录",
};

export function MyRecordsPage({ onResume }: { onResume: (sessionId: string) => void }) {
  const [pending, setPending] = useState<CaptureSessionSummary[]>([]);
  const [items, setItems] = useState<Array<ExperienceContent & { id: string; recorded_at: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  async function loadRecords() {
    setLoading(true); setError(null);
    try {
      const [sessions, experiences] = await Promise.all([listPendingSessions(), listExperiences()]);
      setPending(sessions.filter((session) => session.status !== "confirmed"));
      setItems(experiences);
    } catch { setError("暂时无法读取记录，请稍后重试。"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadRecords(); }, []);
  return <section className="space-y-5 px-5 pb-6 pt-3">
    <div className="flex items-center gap-4 rounded-[2rem] border-2 border-ink bg-lime p-4 shadow-[5px_5px_0_0_#1c2b0a]">
      <span className="h-16 w-16 shrink-0 overflow-hidden rounded-2xl border-2 border-ink bg-cream"><img src={avatar} alt="当前演示贡献者头像" className="h-full w-full object-cover" /></span>
      <div><h1 className="font-display text-xl font-extrabold text-ink">当前演示贡献者</h1><p className="text-xs font-bold text-ink-soft">儿童阅读活动 · 实践记录者</p></div>
    </div>
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-2xl border-2 border-ink bg-cream py-3 text-center shadow-[3px_3px_0_0_#1c2b0a]"><p className="font-display text-2xl font-extrabold text-leaf">{pending.length}</p><p className="text-xs font-bold">待处理</p></div>
      <div className="rounded-2xl border-2 border-ink bg-cream py-3 text-center shadow-[3px_3px_0_0_#1c2b0a]"><p className="font-display text-2xl font-extrabold text-leaf">{items.length}</p><p className="text-xs font-bold">已确认</p></div>
    </div>
    {error && <div className="rounded-2xl border-2 border-red-300 bg-red-50 p-4 text-sm text-red-700"><p>{error}</p><button onClick={() => void loadRecords()} className="mt-3 rounded-full border border-red-700 px-3 py-1 font-bold">重新读取</button></div>}
    <section className="space-y-3"><div className="flex items-end gap-2"><h2 className="font-display text-lg font-extrabold">待处理记录</h2><span className="pb-0.5 text-xs font-bold tracking-widest text-leaf">PENDING</span></div><div className="space-y-2">{loading ? <p className="text-sm text-ink-soft">正在读取记录…</p> : pending.length === 0 ? <div className="rounded-2xl border-2 border-dashed border-ink/20 p-4 text-sm text-ink-soft">暂无待处理记录。</div> : pending.map((item) => item.status === "failed" ? <div key={item.id} className="w-full rounded-2xl border-2 border-red-200 bg-red-50 p-3 text-left"><span className="block text-xs font-bold text-red-700">{STATUS_LABEL[item.status]}</span><span className="mt-1 block line-clamp-2 text-ink">{item.marker_transcript_preview ?? "这段录音未能转写"}</span><span className="mt-2 block text-xs text-red-700">请回到“记一下”重新录制，或改用文字输入。</span></div> : <button key={item.id} onClick={() => onResume(item.id)} className="w-full rounded-2xl border-2 border-ink bg-lime-wash p-3 text-left shadow-[3px_3px_0_0_#1c2b0a]"><span className="block text-xs font-bold text-leaf">{STATUS_LABEL[item.status]}</span><span className="mt-1 block line-clamp-2 font-bold text-ink">{item.marker_transcript_preview ?? "这条记录暂无文字内容"}</span><span className="mt-2 block text-xs text-ink-soft">{STATUS_ACTION[item.status]} ›</span></button>)}</div></section>
    <section className="relative space-y-3 pl-5"><span className="absolute bottom-2 left-[10px] top-10 w-0.5 bg-ink/15" /><div className="flex items-end gap-2"><h2 className="font-display text-lg font-extrabold">最近留下的经验</h2><span className="pb-0.5 text-xs font-bold tracking-widest text-leaf">TIMELINE</span></div>{items.length === 0 ? <div className="rounded-2xl border-2 border-dashed border-ink/20 p-4 text-sm text-ink-soft">确认后的经验会在这里留下时间线。</div> : items.map((item) => <article key={item.id} className="relative rounded-2xl border-2 border-ink bg-cream p-4 shadow-[3px_3px_0_0_#1c2b0a]"><span className="absolute -left-4 top-6 z-10 h-3 w-3 rounded-full border-2 border-ink bg-lime" /><p className="text-xs font-bold text-ink-soft">{new Date(item.recorded_at).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })} · 儿童阅读活动</p><h3 className="mt-2 font-bold text-ink">{item.context ?? "一条已确认经验"}</h3>{item.action_and_reason && <p className="mt-2 line-clamp-2 text-sm text-ink-soft">{item.action_and_reason}</p>}</article>)}</section>
  </section>;
}
