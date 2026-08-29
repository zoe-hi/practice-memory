const STEPS = [
  { icon: "🎧", title: "记一下", desc: "用一句几秒的语音或文字，说说现场发生的一个变化。" },
  { icon: "💬", title: "AI 复盘", desc: "回答几个针对性的问题，一次一个，帮你把经过讲清楚。" },
  { icon: "🗂️", title: "确认经验卡", desc: "检查 AI 整理的事实与推断，确认后留存为一条经验。" },
] as const;

export function Onboarding({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      className="absolute inset-0 z-30 flex items-end bg-ink/40 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="快速了解经验捕手"
    >
      <div className="w-full space-y-5 rounded-t-[2rem] border-t-2 border-ink bg-cream px-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-6 shadow-[0_-6px_0_0_#1c2b0a]">
        <div className="space-y-1">
          <p className="text-xs font-bold tracking-widest text-leaf">快速开始</p>
          <h2 className="font-display text-2xl font-extrabold text-ink">三步走完一条经验</h2>
          <p className="text-sm text-ink-soft">从一句现场记录，到有情境、有边界的实践经验。</p>
        </div>
        <ol className="space-y-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex items-start gap-3 rounded-2xl border-2 border-ink bg-lime-wash p-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border-2 border-ink bg-lime text-lg shadow-[2px_2px_0_0_#1c2b0a]">
                {step.icon}
              </span>
              <span className="flex-1">
                <span className="block text-sm font-bold text-ink">
                  {index + 1}. {step.title}
                </span>
                <span className="mt-0.5 block text-xs leading-5 text-ink-soft">{step.desc}</span>
              </span>
            </li>
          ))}
        </ol>
        <button
          onClick={onDismiss}
          className="w-full rounded-full border-2 border-ink bg-lime px-5 py-3 text-sm font-bold shadow-[3px_3px_0_0_#1c2b0a]"
        >
          开始记录第一条
        </button>
        <button onClick={onDismiss} className="w-full text-center text-xs font-bold text-ink-soft">
          跳过
        </button>
      </div>
    </div>
  );
}
