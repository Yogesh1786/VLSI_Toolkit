// Core building blocks. Every page is made of these, so the app stays consistent.
import { useState, type ReactNode } from "react";
import {
  Check, CircleCheck, CircleX, Copy, Download, Info, LoaderCircle, TriangleAlert, type LucideIcon,
} from "lucide-react";
import { cx, downloadText, STATUS_TONE, TONE_HEX, type Tone } from "../lib/format";

// ---------------------------------------------------------------- layout

export function PageHeader({ area, title, description, icon: Icon, actions }: {
  area: string; title: string; description: ReactNode; icon: LucideIcon; actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start gap-4">
      <div className="grid size-12 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[#6d8ff5] to-[#2f5bd3] text-white shadow-lg shadow-blue-600/25">
        <Icon className="size-6" strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">{area}</div>
        <h1 className="text-[26px] font-bold leading-tight tracking-tight">{title}</h1>
        <p className="mt-1 max-w-3xl text-[14.5px] text-muted">{description}</p>
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, subtitle, actions, children, className, bodyClass }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={cx("rounded-xl border border-line bg-surface shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3.5">
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-[15px] font-semibold">{title}</h2>}
            {subtitle && <p className="text-[13px] text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={cx("p-5", bodyClass)}>{children}</div>
    </section>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">{children}</div>;
}

// ---------------------------------------------------------------- KPIs

const toneText: Record<Tone, string> = {
  good: "text-good bg-good/10", bad: "text-bad bg-bad/10", warn: "text-warn bg-warn/12",
  info: "text-info bg-info/10", neutral: "text-muted bg-surface-3",
};

export type KpiItem = { label: string; value: ReactNode; note?: ReactNode; tone?: Tone; hint?: string };

export function Kpi({ label, value, note, tone = "neutral", hint }: KpiItem) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-card" title={hint}>
      <div className="truncate text-[11px] font-semibold uppercase tracking-[0.1em] text-faint">{label}</div>
      <div className="mt-1.5 truncate text-[24px] font-semibold leading-tight tracking-tight tabular-nums">{value}</div>
      {note != null && note !== "" && (
        <span className={cx("mt-2 inline-block max-w-full truncate rounded-md px-2 py-0.5 text-[12px] font-medium",
          toneText[tone])}>
          {note}
        </span>
      )}
    </div>
  );
}

export function KpiGrid({ items }: { items: KpiItem[] }) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      {items.map((k) => <Kpi key={k.label} {...k} />)}
    </div>
  );
}

// ---------------------------------------------------------------- badges

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[12px] font-semibold",
      toneText[tone], className)}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  const Icon = tone === "good" ? CircleCheck : tone === "bad" ? CircleX : tone === "warn" ? TriangleAlert : Info;
  return <Badge tone={tone}><Icon className="size-3.5" />{status}</Badge>;
}

// ---------------------------------------------------------------- tabs

export type TabDef = { id: string; label: string; icon?: LucideIcon; count?: number };

export function Tabs({ tabs, active, onChange }: { tabs: TabDef[]; active: string; onChange: (id: string) => void }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map(({ id, label, icon: Icon, count }) => (
        <button key={id} onClick={() => onChange(id)}
          className={cx("relative flex shrink-0 items-center gap-2 px-3.5 py-2.5 text-[14px] font-medium transition-colors",
            active === id ? "text-brand" : "text-muted hover:text-fg")}>
          {Icon && <Icon className="size-4" />}
          {label}
          {count != null && (
            <span className={cx("rounded-full px-1.5 text-[11px] font-semibold",
              active === id ? "bg-brand-soft text-brand" : "bg-surface-3 text-muted")}>{count}</span>
          )}
          {active === id && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-brand" />}
        </button>
      ))}
    </div>
  );
}

export function useTabs(first: string) {
  return useState(first);
}

// ---------------------------------------------------------------- controls

export function Button({ children, onClick, variant = "secondary", icon: Icon, disabled, title, className }: {
  children?: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost"; icon?: LucideIcon;
  disabled?: boolean; title?: string; className?: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-[13.5px] font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-brand text-white shadow-sm hover:brightness-110",
        variant === "secondary" && "border border-line bg-surface text-fg shadow-card hover:border-line-strong hover:bg-surface-2",
        variant === "ghost" && "text-muted hover:bg-surface-3 hover:text-fg",
        className)}>
      {Icon && <Icon className="size-4" />}
      {children}
    </button>
  );
}

export function DownloadButton({ name, text, mime, label, primary }: {
  name: string; text: string; mime?: string; label?: string; primary?: boolean;
}) {
  return (
    <Button variant={primary ? "primary" : "secondary"} icon={Download} onClick={() => downloadText(name, text, mime)}>
      {label ?? name}
    </Button>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button variant="ghost" icon={done ? Check : Copy} title="Copy to clipboard"
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}>
      {done ? "Copied" : "Copy"}
    </Button>
  );
}

export function Segmented<T extends string>({ options, value, onChange, size = "md" }: {
  options: { value: T; label: string; icon?: LucideIcon }[]; value: T; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map(({ value: v, label, icon: Icon }) => (
        <button key={v} onClick={() => onChange(v)}
          className={cx("inline-flex items-center gap-1.5 rounded-md font-medium transition-all",
            size === "sm" ? "px-2.5 py-1 text-[12.5px]" : "px-3 py-1.5 text-[13px]",
            value === v ? "bg-surface text-fg shadow-card" : "text-muted hover:text-fg")}>
          {Icon && <Icon className="size-3.5" />}
          {label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 flex items-center gap-1 text-[13px] font-medium text-muted" title={hint}>
        {label}{hint && <Info className="size-3.5 text-faint" />}
      </span>
      {children}
    </label>
  );
}

const inputCls = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-[14px] outline-none transition focus:border-brand focus:ring-3 focus:ring-brand/15";

export function Select({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function TextInput({ value, onChange, placeholder, mono }: {
  value: string; onChange: (v: string) => void; placeholder?: string; mono?: boolean;
}) {
  return <input className={cx(inputCls, mono && "font-mono text-[13px]")} value={value} placeholder={placeholder}
    onChange={(e) => onChange(e.target.value)} />;
}

export function NumberInput({ value, onChange, min, max, step = 1 }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number;
}) {
  return <input type="number" className={cx(inputCls, "tabular-nums")} value={value} min={min} max={max} step={step}
    onChange={(e) => onChange(Number(e.target.value))} />;
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 text-[13.5px] text-muted">
      <span className={cx("relative h-5 w-9 rounded-full transition-colors", checked ? "bg-brand" : "bg-line-strong")}>
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "left-4.5" : "left-0.5")} />
      </span>
      {label}
    </button>
  );
}

export function Chips<T extends string>({ options, selected, onChange }: {
  options: { value: T; label: string; tone?: Tone; count?: number }[]; selected: T[]; onChange: (v: T[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(({ value, label, tone, count }) => {
        const on = selected.includes(value);
        return (
          <button key={value} onClick={() => onChange(on ? selected.filter((s) => s !== value) : [...selected, value])}
            className={cx("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] font-medium transition",
              on ? "border-brand/40 bg-brand-soft text-brand" : "border-line bg-surface text-muted hover:text-fg")}>
            {tone && <span className="size-2 rounded-full" style={{ background: TONE_HEX[tone] }} />}
            {label}{count != null && <span className="opacity-70">{count}</span>}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- feedback

export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: ReactNode; children?: ReactNode }) {
  const Icon = tone === "good" ? CircleCheck : tone === "bad" ? CircleX : tone === "warn" ? TriangleAlert : Info;
  const border = { good: "border-good/30", bad: "border-bad/30", warn: "border-warn/35", info: "border-info/30", neutral: "border-line" }[tone];
  const bg = { good: "bg-good/6", bad: "bg-bad/6", warn: "bg-warn/8", info: "bg-info/6", neutral: "bg-surface-2" }[tone];
  const color = { good: "text-good", bad: "text-bad", warn: "text-warn", info: "text-info", neutral: "text-muted" }[tone];
  return (
    <div className={cx("mb-3 flex gap-3 rounded-lg border px-4 py-3 text-[14px]", border, bg)}>
      <Icon className={cx("mt-0.5 size-4.5 shrink-0", color)} />
      <div className="min-w-0">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={cx(title ? "text-muted" : "", "break-words")}>{children}</div>}
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface/60 px-6 py-14 text-center">
      <div className="mb-3 grid size-12 place-items-center rounded-full bg-brand-soft text-brand"><Icon className="size-6" /></div>
      <div className="font-semibold">{title}</div>
      {text && <p className="mt-1 max-w-md text-[14px] text-muted">{text}</p>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cx("size-4 animate-spin text-brand", className)} />;
}

export function LoadingBlock({ label = "Analyzing…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 rounded-xl border border-line bg-surface py-16 text-muted shadow-card">
      <Spinner className="size-5" /> {label}
    </div>
  );
}

/** Horizontal bar split into colored segments, with a legend. */
export function StackedBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full bg-surface-3">
        {parts.filter((p) => p.value > 0).map((p) => (
          <div key={p.label} title={`${p.label}: ${p.value}`} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />
        ))}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: p.color }} />
            <span className="text-muted">{p.label}</span>
            <b className="tabular-nums">{p.value}</b>
            <span className="text-faint">({Math.round((p.value / total) * 100)}%)</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Simple horizontal bar list (cell mix etc.). */
export function BarList({ items, format = (v: number) => v.toLocaleString("en-US") }: {
  items: { label: string; value: number }[]; format?: (v: number) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="space-y-2.5">
      {items.map((i) => (
        <div key={i.label}>
          <div className="mb-1 flex justify-between text-[13px]">
            <span className="text-muted">{i.label}</span><span className="font-medium tabular-nums">{format(i.value)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-3">
            <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${(i.value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
