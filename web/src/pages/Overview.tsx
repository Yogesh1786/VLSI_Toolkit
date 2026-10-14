import { Link } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  FileUp,
  LayoutGrid,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { AREAS, TOOLS } from "../tools";

const STEPS = [
  {
    icon: LayoutGrid,
    title: "Pick a tool",
    text: "From the sidebar, the cards below, or press Ctrl + K.",
  },
  {
    icon: FileUp,
    title: "Load a file",
    text: "Every tool opens with a working example. Drop in your own file any time.",
  },
  {
    icon: Sparkles,
    title: "Review & export",
    text: "Read the summary, drill into the tabs, download the results.",
  },
];

export default function Overview() {
  return (
    <div>
      <section
        className="relative mb-8 overflow-hidden rounded-2xl px-8 py-9 text-white shadow-xl shadow-blue-950/20"
        style={{
          background:
            "radial-gradient(120% 140% at 100% 0%, #3d6af0 0%, #213f9e 45%, #0f1b33 100%)",
        }}
      >
        <svg
          className="absolute -top-6 right-0 h-[130%] opacity-[0.13]"
          viewBox="0 0 300 200"
          fill="none"
          stroke="white"
          strokeWidth="1.2"
        >
          {Array.from({ length: 9 }, (_, i) => (
            <path key={i} d={`M${20 + i * 30},0 v40 h20 v60 h-20 v100`} />
          ))}
          {Array.from({ length: 6 }, (_, i) => (
            <circle key={i} cx={40 + i * 45} cy={100 + (i % 2) * 30} r="4" />
          ))}
          <rect x="110" y="60" width="80" height="80" rx="8" />
        </svg>
        <div className="relative max-w-2xl">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[12px] font-medium">
            <ShieldCheck className="size-3.5" /> Runs 100% locally on your
            computer
          </div>
          <h1 className="text-[34px] font-bold tracking-tight">VLSI Toolkit</h1>
          <p className="mt-2 text-[16px] text-white/80">
            A workbench for everyday chip-design work: lint RTL, triage
            regressions, read timing and placement reports, and check analog
            netlists, all in one place.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/lint"
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-[14px] font-semibold text-[#1d3a8f] shadow hover:bg-white/90"
            >
              Try RTL Lint <ArrowRight className="size-4" />
            </Link>
            <Link
              to="/regression"
              className="inline-flex items-center gap-2 rounded-lg border border-white/30 px-4 py-2 text-[14px] font-medium hover:bg-white/10"
            >
              Triage a regression
            </Link>
          </div>
        </div>
        <div className="relative mt-8 flex flex-wrap gap-8 text-[13px] text-white/70">
          <div>
            <b className="block text-[22px] text-white">{TOOLS.length}</b>tools
          </div>
          <div>
            <b className="block text-[22px] text-white">{AREAS.length}</b>design
            areas
          </div>
          <div>
            <b className="block text-[22px] text-white">0</b>extra EDA licenses
          </div>
        </div>
      </section>

      <div className="grid gap-5 md:grid-cols-2">
        {AREAS.map((a) => (
          <section
            key={a.name}
            className="rounded-xl border border-line bg-surface p-5 shadow-card"
          >
            <div className="mb-1 flex items-center gap-2 text-[16px] font-semibold">
              <Boxes className="size-4.5 text-brand" />
              {a.name}
            </div>
            <p className="mb-4 text-[13.5px] text-muted">{a.blurb}</p>
            <div className="space-y-1.5">
              {TOOLS.filter((t) => t.area === a.name).map((t) => (
                <Link
                  key={t.path}
                  to={t.path}
                  className="group flex items-center gap-3 rounded-lg border border-transparent p-2.5 transition hover:border-line hover:bg-surface-2"
                >
                  <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                    <t.icon className="size-4.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[14px] font-medium">{t.title}</div>
                    <div className="truncate text-[12.5px] text-muted">
                      {t.description}
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-faint opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>

      <h2 className="mt-10 mb-4 text-[16px] font-semibold">Quick start</h2>
      <div className="grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <div
            key={s.title}
            className="flex gap-3 rounded-xl border border-line bg-surface p-4 shadow-card"
          >
            <div className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-[14px] font-bold text-brand">
              {i + 1}
            </div>
            <div>
              <div className="font-medium">{s.title}</div>
              <div className="text-[13.5px] text-muted">{s.text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
