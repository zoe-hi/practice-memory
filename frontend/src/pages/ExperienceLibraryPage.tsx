import { useEffect, useState } from "react";
import { listExperiences, requestDecisionSupport } from "@/api/capture";
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
  const [result, setResult] = useState<DecisionSupportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExperiences().then(setItems).catch(() => setError("暂时无法读取经验库，请稍后重试。")).finally(() => setLoading(false));
  }, []);

  async function requestSupport() {
    if (!concern.trim()) return;
    setRequesting(true); setError(null); setResult(null);
    try { setResult(await requestDecisionSupport(concern.trim())); }
    catch (reason) { setError(reason instanceof RequestError ? reason.message : "暂时无法获取经验参考，请重试。"); }
    finally { setRequesting(false); }
  }

  return <section className="space-y-5 px-5 py-6">
    <div className="relative overflow-hidden rounded-[2rem] border-2 border-ink bg-lime p-5 shadow-[5px_5px_0_0_#1c2b0a]">
      <img src={mascot} alt="经验捕手吉祥物" className="animate-bob pointer-events-none absolute -right-8 bottom-[-24px] w-48 drop-shadow-xl" />
      <div className="relative z-10 max-w-[62%]"><span className="inline-flex rounded-full border-2 border-ink bg-cream px-3 py-1 text-xs font-bold">儿童阅读活动</span><h1 className="mt-3 font-display text-3xl font-extrabold leading-tight text-ink">经验会继续<br />生长</h1><p className="mt-2 text-xs leading-5 text-ink-soft">把经确认的现场记录留下来，在下一次犹豫时带回来参考。</p></div>
    </div>

    <div className="space-y-3 rounded-2xl border-2 border-ink bg-lime-wash p-4">
      <p className="font-bold text-ink">遇到拿不准的现场情况？</p>
      <textarea value={concern} onChange={(event) => setConcern(event.target.value)} rows={4} placeholder="例如：孩子站在门口，没有进入共读区域，我该继续围坐还是先让他们自由选书？" className="w-full resize-none rounded-xl border-2 border-ink bg-cream p-3 text-sm outline-none" />
      <button onClick={requestSupport} disabled={!concern.trim() || requesting} className="w-full rounded-full border-2 border-ink bg-lime px-4 py-2 text-sm font-bold disabled:opacity-60">{requesting ? "正在查找经验…" : "查找相似经验"}</button>
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
