import { useState } from "react";
import { CapturePage } from "@/pages/CapturePage";
import { ExperienceLibraryPage } from "@/pages/ExperienceLibraryPage";
import { MyRecordsPage } from "@/pages/MyRecordsPage";
import navMic from "@/imports/capture-nav-mic.svg";
import navMicInactive from "@/imports/capture-nav-mic-inactive.svg";
import navLibrary from "@/imports/capture-nav-mine.svg";
import navLibraryActive from "@/imports/capture-nav-mine-active.svg";
import navMine from "@/imports/capture-nav-theme.svg";
import navMineActive from "@/imports/capture-nav-theme-active.svg";

const tabs = [
  { key: "capture", icon: navMicInactive, activeIcon: navMic, label: "记一下" },
  { key: "library", icon: navLibrary, activeIcon: navLibraryActive, label: "经验库" },
  { key: "mine", icon: navMine, activeIcon: navMineActive, label: "我的" },
] as const;

type TabKey = (typeof tabs)[number]["key"];

export default function App() {
  const [tab, setTab] = useState<TabKey>("capture");
  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null);

  function resumeCapture(sessionId: string) {
    setResumeSessionId(sessionId);
    setTab("capture");
  }
  return (
    <div className="flex h-screen w-full justify-center bg-lime-wash/40 sm:items-center sm:p-4">
      <div className="relative flex h-full w-full max-w-[440px] flex-col overflow-hidden bg-cream shadow-2xl sm:h-[min(900px,calc(100vh-2rem))] sm:rounded-[2.5rem] sm:border-2 sm:border-ink">
        <header className="flex shrink-0 items-center justify-between px-6 pb-2 pt-[max(0.9rem,env(safe-area-inset-top))] text-xs font-bold text-ink/65">
          <span>9:41</span>
          <span className="tracking-[0.2em]">◫ ◫ ◫</span>
        </header>
        <main className="flex-1 overflow-y-auto">
          {tab === "capture" && <CapturePage resumeSessionId={resumeSessionId} onConfirmed={() => { setResumeSessionId(null); setTab("mine"); }} />}
          {tab === "library" && <ExperienceLibraryPage />}
          {tab === "mine" && <MyRecordsPage onResume={resumeCapture} />}
        </main>
        <nav className="z-20 shrink-0 border-t-2 border-ink bg-cream/95 px-6 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur">
            <div className="flex justify-between">
              {tabs.map((t) => {
                const on = tab === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className="flex flex-1 flex-col items-center gap-0.5"
                  >
                    <span
                      className={`flex h-11 w-11 items-center justify-center rounded-2xl text-xl transition ${
                        on ? "rounded-[14px] border-2 border-ink bg-lime shadow-[2px_2px_0_0_#1c2b0a]" : "opacity-100"
                      }`}
                    >
                      <img src={on ? t.activeIcon : t.icon} alt="" className="h-[26px] w-[26px]" />
                    </span>
                    <span className={`text-[10px] font-bold ${on ? "text-ink" : "text-ink-soft"}`}>
                      {t.label}
                    </span>
                  </button>
                );
              })}
            </div>
        </nav>
      </div>
    </div>
  );
}
