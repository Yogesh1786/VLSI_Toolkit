import { useMemo, useState } from "react";
import {
  Activity, ArrowLeftRight, Calculator, Cable, Clock, Gauge, Layers, RadioTower, Search, ShieldAlert, Timer, Zap, type LucideIcon,
} from "lucide-react";
import { Chips, PageHeader } from "../components/ui";
import { cx, type Tone } from "../lib/format";

// ---------------------------------------------------------------- calculator definitions

type Field = { key: string; label: string; unit: string; value: number; step?: number; hint?: string };
type Out = { label: string; value: string; tone?: Tone; main?: boolean };
type Calc = {
  id: string; title: string; icon: LucideIcon; tag: string; blurb: string;
  fields: Field[]; compute: (v: Record<string, number>) => Out[]; formula: string; note?: string;
};

/** Number with up to 4 significant digits, no exponent for everyday ranges. */
function num(v: number, digits = 4): string {
  if (!Number.isFinite(v)) return "∞";
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e7 || a < 1e-4)) return v.toExponential(2).replace("e+", "e");
  return Number(v.toPrecision(digits)).toLocaleString("en-US", { maximumFractionDigits: 6 });
}
const SEC_PER_YEAR = 365.25 * 24 * 3600;

function duration(seconds: number): string {
  if (!Number.isFinite(seconds)) return "∞";
  if (seconds < 60) return `${num(seconds)} s`;
  if (seconds < 3600) return `${num(seconds / 60)} min`;
  if (seconds < 86400) return `${num(seconds / 3600)} h`;
  if (seconds < SEC_PER_YEAR) return `${num(seconds / 86400)} days`;
  return `${num(seconds / SEC_PER_YEAR)} years`;
}

const CALCS: Calc[] = [
  {
    id: "clock", title: "Clock period & frequency", icon: Clock, tag: "Timing",
    blurb: "Period, high and low time of a clock.",
    fields: [
      { key: "f", label: "Frequency", unit: "MHz", value: 500 },
      { key: "duty", label: "Duty cycle", unit: "%", value: 50 },
    ],
    compute: ({ f, duty }) => {
      const t = 1000 / f;
      return [
        { label: "Period", value: `${num(t)} ns`, main: true },
        { label: "High time", value: `${num((t * duty) / 100)} ns` },
        { label: "Low time", value: `${num((t * (100 - duty)) / 100)} ns` },
      ];
    },
    formula: "T = 1 / f",
  },
  {
    id: "slack", title: "Setup & hold slack", icon: Timer, tag: "Timing",
    blurb: "Slack of one register-to-register path and the fastest clock it can run at.",
    fields: [
      { key: "T", label: "Clock period", unit: "ns", value: 2 },
      { key: "tcq", label: "Clock-to-Q (max)", unit: "ns", value: 0.12 },
      { key: "tl", label: "Logic delay (max)", unit: "ns", value: 1.45 },
      { key: "tsu", label: "Setup time", unit: "ns", value: 0.06 },
      { key: "skew", label: "Clock skew (capture − launch)", unit: "ns", value: 0.03, hint: "Positive skew helps setup and hurts hold." },
      { key: "unc", label: "Uncertainty (jitter)", unit: "ns", value: 0.1 },
      { key: "tcqmin", label: "Clock-to-Q (min)", unit: "ns", value: 0.08 },
      { key: "tlmin", label: "Logic delay (min)", unit: "ns", value: 0.05 },
      { key: "th", label: "Hold time", unit: "ns", value: 0.04 },
    ],
    compute: ({ T, tcq, tl, tsu, skew, unc, tcqmin, tlmin, th }) => {
      const setup = T + skew - (tcq + tl + tsu + unc);
      const hold = tcqmin + tlmin - (th + skew + unc);
      const fmax = 1000 / (tcq + tl + tsu + unc - skew);
      return [
        { label: "Setup slack", value: `${num(setup)} ns`, tone: setup >= 0 ? "good" : "bad", main: true },
        { label: "Hold slack", value: `${num(hold)} ns`, tone: hold >= 0 ? "good" : "bad", main: true },
        { label: "Max frequency", value: `${num(fmax)} MHz` },
      ];
    },
    formula: "setup = T + skew − (tcq + tlogic + tsu + unc)     hold = tcq,min + tlogic,min − (th + skew + unc)",
  },
  {
    id: "mtbf", title: "Synchronizer MTBF", icon: ShieldAlert, tag: "CDC",
    blurb: "How often a flip-flop synchronizer is expected to fail from metastability.",
    fields: [
      { key: "fc", label: "Receiving clock", unit: "MHz", value: 500 },
      { key: "fd", label: "Data toggle rate", unit: "MHz", value: 50 },
      { key: "n", label: "Synchronizer flops", unit: "stages", value: 2, step: 1 },
      { key: "tau", label: "τ (resolution constant)", unit: "ps", value: 20, hint: "From the library/foundry; 10–30 ps for modern nodes." },
      { key: "t0", label: "T0 (metastability window)", unit: "ps", value: 50 },
      { key: "ovh", label: "Flop overhead (tsu + tcq)", unit: "ns", value: 0.15 },
    ],
    compute: ({ fc, fd, n, tau, t0, ovh }) => {
      const tr = Math.max(0, (Math.max(1, n) - 1) * (1000 / fc) - ovh) * 1e-9;   // resolution time, s
      const mtbf = Math.exp(tr / (tau * 1e-12)) / (t0 * 1e-12 * fc * 1e6 * fd * 1e6);
      const years = mtbf / SEC_PER_YEAR;
      return [
        { label: "MTBF", value: duration(mtbf), tone: years > 1e3 ? "good" : years > 10 ? "warn" : "bad", main: true },
        { label: "Resolution time", value: `${num(tr * 1e9)} ns` },
        { label: "Verdict", value: years > 1e3 ? "safe" : years > 10 ? "marginal: add a stage" : "unsafe: add stages", tone: years > 1e3 ? "good" : years > 10 ? "warn" : "bad" },
      ];
    },
    formula: "MTBF = e^(tr / τ) / (T0 · fclk · fdata),   tr = (N − 1) · Tclk − (tsu + tcq)",
    note: "With 1 flop there is no resolution time: always use at least 2.",
  },
  {
    id: "fifo", title: "FIFO depth", icon: Layers, tag: "CDC",
    blurb: "Minimum depth of an async FIFO that must absorb a write burst.",
    fields: [
      { key: "fw", label: "Write clock", unit: "MHz", value: 200 },
      { key: "fr", label: "Read clock", unit: "MHz", value: 100 },
      { key: "b", label: "Burst length", unit: "words", value: 120, step: 1 },
      { key: "iw", label: "Idle cycles between writes", unit: "cycles", value: 0, step: 1 },
      { key: "ir", label: "Idle cycles between reads", unit: "cycles", value: 1, step: 1 },
      { key: "sync", label: "Synchronizer latency margin", unit: "words", value: 4, step: 1, hint: "Pointer synchronization delays the full/empty flags by a few cycles." },
    ],
    compute: ({ fw, fr, b, iw, ir, sync }) => {
      const tBurst = (b * (1 + iw)) / fw;                 // µs to write the burst
      const read = Math.floor(tBurst * (fr / (1 + ir)));    // words read meanwhile
      const depth = Math.max(1, Math.ceil(b - Math.min(read, b))) + sync;
      const pow2 = 2 ** Math.ceil(Math.log2(depth));
      return [
        { label: "Minimum depth", value: `${depth} words`, main: true },
        { label: "Power of two", value: `${pow2} words` },
        { label: "Read during burst", value: `${Math.min(read, b)} of ${b}` },
      ];
    },
    formula: "depth = B − B·(1 + idle_w)/f_w · f_r/(1 + idle_r) + margin",
  },
  {
    id: "power", title: "Dynamic power", icon: Zap, tag: "Power",
    blurb: "Switching power of a block from activity, capacitance, voltage and frequency.",
    fields: [
      { key: "a", label: "Activity factor α", unit: "", value: 0.15, hint: "Fraction of the capacitance switching each cycle; 0.1–0.2 for logic, 1 for clocks." },
      { key: "c", label: "Switched capacitance", unit: "pF", value: 800 },
      { key: "v", label: "Supply voltage", unit: "V", value: 0.9 },
      { key: "f", label: "Clock frequency", unit: "MHz", value: 1000 },
      { key: "leak", label: "Leakage", unit: "mW", value: 3 },
    ],
    compute: ({ a, c, v, f, leak }) => {
      const pdyn = a * c * 1e-12 * v * v * f * 1e6 * 1e3;  // mW
      return [
        { label: "Dynamic power", value: `${num(pdyn)} mW`, main: true },
        { label: "Total (with leakage)", value: `${num(pdyn + leak)} mW` },
        { label: "At +10% VDD", value: `${num(pdyn * 1.21 + leak)} mW` },
      ];
    },
    formula: "P = α · C · V² · f   (+ leakage)",
    note: "Power grows with V²: a 10% voltage increase costs 21% more dynamic power.",
  },
  {
    id: "wire", title: "Wire RC delay", icon: Cable, tag: "Physical",
    blurb: "Delay of a driver, a distributed RC wire and a load (Elmore, 50% point).",
    fields: [
      { key: "len", label: "Wire length", unit: "µm", value: 1000 },
      { key: "r", label: "Wire resistance", unit: "Ω/µm", value: 0.8 },
      { key: "c", label: "Wire capacitance", unit: "fF/µm", value: 0.2 },
      { key: "rd", label: "Driver resistance", unit: "Ω", value: 1500 },
      { key: "cl", label: "Load capacitance", unit: "fF", value: 5 },
    ],
    compute: ({ len, r, c, rd, cl }) => {
      const rw = r * len, cw = c * len * 1e-15, cL = cl * 1e-15;
      const d = 0.69 * rd * (cw + cL) + 0.38 * rw * cw + 0.69 * rw * cL;
      return [
        { label: "Delay (50%)", value: `${num(d * 1e12)} ps`, main: true },
        { label: "Wire R", value: `${num(rw)} Ω` },
        { label: "Wire C", value: `${num(cw * 1e15)} fF` },
      ];
    },
    formula: "t50 = 0.69·Rd·(Cw + CL) + 0.38·Rw·Cw + 0.69·Rw·CL",
    note: "Wire delay grows with length²: a long net usually needs repeaters.",
  },
  {
    id: "ir", title: "IR drop", icon: Activity, tag: "Physical",
    blurb: "Voltage lost in the power grid for a given current draw.",
    fields: [
      { key: "p", label: "Block power", unit: "mW", value: 450 },
      { key: "v", label: "Supply voltage", unit: "V", value: 0.9 },
      { key: "r", label: "Effective grid resistance", unit: "mΩ", value: 60 },
    ],
    compute: ({ p, v, r }) => {
      const i = p / 1000 / v;
      const drop = i * r / 1000;
      const pct = (drop / v) * 100;
      return [
        { label: "IR drop", value: `${num(drop * 1000)} mV`, main: true, tone: pct > 10 ? "bad" : pct > 5 ? "warn" : "good" },
        { label: "% of VDD", value: `${num(pct, 3)} %`, tone: pct > 10 ? "bad" : pct > 5 ? "warn" : "good" },
        { label: "Current", value: `${num(i * 1000)} mA` },
      ];
    },
    formula: "I = P / V,   ΔV = I · R",
    note: "A common sign-off budget is 5% static IR drop (10% including dynamic).",
  },
  {
    id: "gmid", title: "gm/Id transistor sizing", icon: Gauge, tag: "Analog",
    blurb: "First-cut MOSFET sizing from a target current and gm/Id (square-law approximation).",
    fields: [
      { key: "id", label: "Drain current Id", unit: "µA", value: 100 },
      { key: "g", label: "gm/Id", unit: "S/A", value: 12, hint: "5–10 strong inversion (fast), 15–25 weak inversion (efficient)." },
      { key: "lam", label: "λ (channel-length modulation)", unit: "1/V", value: 0.1 },
      { key: "k", label: "µCox", unit: "µA/V²", value: 280 },
    ],
    compute: ({ id, g, lam, k }) => {
      const gm = g * id;                      // µS
      const vov = 2 / g;                      // V (strong inversion)
      const wl = (2 * id) / (k * vov * vov);
      const gain = g / lam;
      return [
        { label: "gm", value: `${num(gm)} µS`, main: true },
        { label: "W/L", value: num(wl, 3), main: true },
        { label: "Vov ≈ 2/(gm/Id)", value: `${num(vov * 1000)} mV` },
        { label: "Intrinsic gain gm·ro", value: `${num(gain, 3)} (${num(20 * Math.log10(gain), 3)} dB)` },
      ];
    },
    formula: "gm = (gm/Id)·Id,   Vov ≈ 2/(gm/Id),   W/L = 2·Id / (µCox·Vov²),   A0 = (gm/Id)/λ",
    note: "Square-law estimates; refine with your PDK's gm/Id lookup tables, especially in weak inversion.",
  },
  {
    id: "bw", title: "Bus bandwidth", icon: ArrowLeftRight, tag: "Interface",
    blurb: "Peak and effective throughput of an AXI/AHB/custom data bus.",
    fields: [
      { key: "w", label: "Data width", unit: "bits", value: 128, step: 8 },
      { key: "f", label: "Clock", unit: "MHz", value: 400 },
      { key: "eff", label: "Efficiency", unit: "%", value: 80, hint: "Fraction of cycles with a data beat (handshake stalls, bubbles)." },
    ],
    compute: ({ w, f, eff }) => {
      const peak = (w / 8) * f;   // MB/s
      return [
        { label: "Effective", value: peak * eff / 100 >= 1000 ? `${num((peak * eff) / 100000)} GB/s` : `${num((peak * eff) / 100)} MB/s`, main: true },
        { label: "Peak", value: peak >= 1000 ? `${num(peak / 1000)} GB/s` : `${num(peak)} MB/s` },
        { label: "Bytes per beat", value: `${num(w / 8)} B` },
      ];
    },
    formula: "throughput = width/8 · f · efficiency",
  },
  {
    id: "dbm", title: "dBm ↔ mW ↔ volts", icon: RadioTower, tag: "Analog",
    blurb: "RF/mixed-signal power units, including RMS voltage across a load.",
    fields: [
      { key: "dbm", label: "Power", unit: "dBm", value: 0 },
      { key: "r", label: "Load", unit: "Ω", value: 50 },
    ],
    compute: ({ dbm, r }) => {
      const mw = 10 ** (dbm / 10);
      const vrms = Math.sqrt((mw / 1000) * r);
      return [
        { label: "Power", value: `${num(mw)} mW`, main: true },
        { label: "Vrms", value: `${num(vrms * 1000)} mV` },
        { label: "Vpeak-peak (sine)", value: `${num(vrms * 2 * Math.SQRT2 * 1000)} mV` },
      ];
    },
    formula: "P[mW] = 10^(dBm/10),   Vrms = √(P · R)",
  },
];

const TAGS = ["Timing", "CDC", "Power", "Physical", "Analog", "Interface"];

// ---------------------------------------------------------------- UI

function CalcCard({ c }: { c: Calc }) {
  const [v, setV] = useState<Record<string, number>>(() => Object.fromEntries(c.fields.map((f) => [f.key, f.value])));
  const valid = c.fields.every((f) => Number.isFinite(v[f.key]));
  const out = useMemo(() => {
    try {
      return valid ? c.compute(v) : [];
    } catch {
      return [];
    }
  }, [c, v, valid]);
  const toneCls: Record<Tone, string> = { good: "text-good", bad: "text-bad", warn: "text-warn", info: "text-info", neutral: "text-fg" };

  return (
    <section className="flex flex-col rounded-xl border border-line bg-surface shadow-card">
      <header className="flex items-start gap-3 border-b border-line px-5 py-3.5">
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
          <c.icon className="size-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold">{c.title}</h2>
          <p className="text-[12.5px] text-muted">{c.blurb}</p>
        </div>
        <span className="rounded-md bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-muted">{c.tag}</span>
      </header>
      <div className="grid flex-1 gap-x-4 gap-y-3 p-5 sm:grid-cols-2">
        {c.fields.map((f) => (
          <label key={f.key} className="block" title={f.hint}>
            <span className="mb-1 flex items-center gap-1 text-[12.5px] font-medium text-muted">
              {f.label}
              {f.hint && <span className="text-faint">ⓘ</span>}
            </span>
            <div className="flex items-center rounded-lg border border-line bg-surface focus-within:border-brand focus-within:ring-3 focus-within:ring-brand/15">
              <input
                type="number"
                step={f.step ?? "any"}
                value={Number.isFinite(v[f.key]) ? v[f.key] : ""}
                onChange={(e) => setV((s) => ({ ...s, [f.key]: e.target.value === "" ? NaN : Number(e.target.value) }))}
                className="min-w-0 flex-1 bg-transparent px-3 py-1.5 text-[14px] tabular-nums outline-none"
              />
              {f.unit && <span className="pr-3 text-[12.5px] text-faint">{f.unit}</span>}
            </div>
          </label>
        ))}
      </div>
      <div className="border-t border-line bg-surface-2 px-5 py-4">
        {out.length === 0 ? (
          <p className="text-[13px] text-muted">Fill in every field.</p>
        ) : (
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {out.map((o) => (
              <div key={o.label}>
                <div className="text-[11px] font-semibold tracking-[0.08em] text-faint uppercase">{o.label}</div>
                <div className={cx("tabular-nums", o.main ? "text-[20px] font-semibold" : "text-[15px] font-medium", toneCls[o.tone ?? "neutral"])}>{o.value}</div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-3 font-mono text-[11.5px] break-words text-muted">{c.formula}</div>
        {c.note && <p className="mt-1.5 text-[12.5px] text-muted">{c.note}</p>}
      </div>
    </section>
  );
}

export default function Calculators() {
  const [q, setQ] = useState("");
  const [tags, setTags] = useState<string[]>(TAGS);
  const shown = CALCS.filter(
    (c) => tags.includes(c.tag) && (!q.trim() || `${c.title} ${c.blurb} ${c.tag}`.toLowerCase().includes(q.trim().toLowerCase())),
  );
  return (
    <>
      <PageHeader area="Utilities" title="Engineer's Calculators" icon={Calculator}
        description="The formulas you reach for every day: clock and slack, synchronizer MTBF, FIFO depth, dynamic power, wire delay, IR drop, gm/Id sizing and more. Results update as you type; nothing is sent to the server." />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search calculators…"
            className="w-full rounded-lg border border-line bg-surface py-1.5 pr-3 pl-9 text-[13.5px] outline-none focus:border-brand focus:ring-3 focus:ring-brand/15" />
        </div>
        <Chips selected={tags} onChange={setTags} options={TAGS.map((t) => ({ value: t, label: t, count: CALCS.filter((c) => c.tag === t).length }))} />
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        {shown.map((c) => <CalcCard key={c.id} c={c} />)}
      </div>
      {shown.length === 0 && <p className="py-10 text-center text-muted">No calculator matches.</p>}
    </>
  );
}
