// "Report" button: turns a page's summary and findings into a standalone, printable report.
// HTML download, or the browser's print dialog for PDF. Everything happens in the browser.
import { useEffect, useRef, useState } from "react";
import { ChevronDown, FileDown, FileText, Printer } from "lucide-react";
import type { Tone } from "../lib/format";

export type ReportKpi = { label: string; value: string | number; note?: string; tone?: Tone };
export type ReportSection =
  | { title: string; kind: "table"; columns: { key: string; label: string; align?: "right" }[]; rows: Record<string, unknown>[]; limit?: number }
  | { title: string; kind: "text"; text: string; mono?: boolean }
  | { title: string; kind: "list"; items: string[] };
export type Report = {
  tool: string;                    // e.g. "SDC Checker"
  title: string;                   // e.g. "Constraints review: uart_top.sdc"
  files?: string[];
  verdict?: { tone: Tone; text: string };
  kpis?: ReportKpi[];
  sections: ReportSection[];
};

const TONE: Record<Tone, string> = { good: "#16803c", bad: "#c62828", warn: "#b45309", info: "#2f5bd3", neutral: "#475569" };

const esc = (v: unknown) =>
  String(v ?? "–").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function cell(v: unknown): string {
  if (v == null || v === "") return "–";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.join(" ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function severityClass(v: string) {
  return /^(ERROR|FAIL|VIOLATED|SLVERR|DECERR)$/.test(v) ? "bad" : /^(WARNING|WARN|INCOMPLETE)$/.test(v) ? "warn" : /^(PASS|MET|OK|OKAY)$/.test(v) ? "good" : "";
}

export function buildReportHtml(r: Report): string {
  const now = new Date();
  const sections = r.sections.map((s) => {
    if (s.kind === "text") return `<h2>${esc(s.title)}</h2><div class="${s.mono ? "mono box" : "box"}">${esc(s.text)}</div>`;
    if (s.kind === "list") return `<h2>${esc(s.title)}</h2><ul>${s.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
    const rows = s.limit ? s.rows.slice(0, s.limit) : s.rows;
    const more = s.limit && s.rows.length > s.limit ? `<p class="muted">… and ${s.rows.length - s.limit} more rows (download the CSV from the tool for all of them).</p>` : "";
    if (!rows.length) return `<h2>${esc(s.title)}</h2><p class="muted">None.</p>`;
    return `<h2>${esc(s.title)} <span class="count">${s.rows.length}</span></h2>
<table><thead><tr>${s.columns.map((c) => `<th${c.align === "right" ? ' class="r"' : ""}>${esc(c.label)}</th>`).join("")}</tr></thead>
<tbody>${rows.map((row) => `<tr>${s.columns.map((c) => {
      const v = cell(row[c.key]);
      const sev = severityClass(v);
      return `<td class="${c.align === "right" ? "r" : ""}">${sev ? `<span class="pill ${sev}">${esc(v)}</span>` : esc(v)}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table>${more}`;
  }).join("\n");
  const kpis = (r.kpis ?? []).map((k) => `<div class="kpi"><div class="kl">${esc(k.label)}</div><div class="kv" style="color:${TONE[k.tone ?? "neutral"]}">${esc(k.value)}</div>${k.note ? `<div class="kn">${esc(k.note)}</div>` : ""}</div>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(r.tool)} report · ${esc(r.title)}</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font: 14px/1.5 "Segoe UI", Inter, system-ui, sans-serif; color: #0f172a; margin: 0; background: #f4f6fb; }
  .page { max-width: 1000px; margin: 24px auto; background: #fff; border: 1px solid #e2e7f0; border-radius: 12px; padding: 36px 40px; }
  header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 2px solid #2f5bd3; padding-bottom: 16px; margin-bottom: 20px; }
  .brand { font-weight: 700; color: #2f5bd3; letter-spacing: .02em; font-size: 12px; text-transform: uppercase; }
  h1 { font-size: 22px; margin: 4px 0 2px; }
  .meta { text-align: right; font-size: 12px; color: #5d6980; }
  .verdict { padding: 12px 16px; border-radius: 8px; font-weight: 600; margin: 0 0 18px; border-left: 5px solid; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; margin-bottom: 8px; }
  .kpi { border: 1px solid #e2e7f0; border-radius: 8px; padding: 10px 12px; }
  .kl { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #8792a8; font-weight: 600; }
  .kv { font-size: 22px; font-weight: 700; }
  .kn { font-size: 12px; color: #5d6980; }
  h2 { font-size: 16px; margin: 26px 0 8px; }
  .count { font-size: 12px; background: #eef2f8; color: #5d6980; border-radius: 10px; padding: 1px 8px; vertical-align: middle; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th { text-align: left; background: #f6f8fc; color: #5d6980; font-weight: 600; border-bottom: 1px solid #cfd7e5; padding: 6px 8px; }
  td { border-bottom: 1px solid #eef2f8; padding: 6px 8px; vertical-align: top; word-break: break-word; }
  .r { text-align: right; font-variant-numeric: tabular-nums; }
  .pill { font-weight: 700; font-size: 11px; padding: 1px 7px; border-radius: 9px; }
  .pill.bad { color: #c62828; background: #fdecec; } .pill.warn { color: #b45309; background: #fdf3e2; } .pill.good { color: #16803c; background: #e7f6ec; }
  .box { border: 1px solid #e2e7f0; border-radius: 8px; padding: 10px 12px; white-space: pre-wrap; }
  .mono { font-family: "Cascadia Code", Consolas, monospace; font-size: 12.5px; }
  .muted { color: #8792a8; font-size: 12.5px; }
  footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #e2e7f0; font-size: 11.5px; color: #8792a8; display: flex; justify-content: space-between; }
  @media print {
    body { background: #fff; }
    .page { margin: 0; border: 0; padding: 0; max-width: none; }
    tr, .kpi { break-inside: avoid; }
    h2 { break-after: avoid; }
    @page { margin: 14mm; }
  }
</style></head><body><div class="page">
<header><div><div class="brand">VLSI Toolkit · ${esc(r.tool)}</div><h1>${esc(r.title)}</h1>
${r.files?.length ? `<div class="muted">Input: ${r.files.map(esc).join(", ")}</div>` : ""}</div>
<div class="meta">${esc(now.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }))}<br>${esc(now.toLocaleTimeString())}</div></header>
${r.verdict ? `<div class="verdict" style="color:${TONE[r.verdict.tone]};border-color:${TONE[r.verdict.tone]};background:${TONE[r.verdict.tone]}12">${esc(r.verdict.text)}</div>` : ""}
${kpis ? `<div class="kpis">${kpis}</div>` : ""}
${sections}
<footer><span>Generated by VLSI Toolkit</span><span>${esc(location.origin)}</span></footer>
</div></body></html>`;
}

function slug(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60) || "report";
}

export function ReportButton({ report }: { report: Report | null }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  if (!report) return null;

  const download = () => {
    const blob = new Blob([buildReportHtml(report)], { type: "text/html" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${slug(report.tool)}_${slug(report.title)}.html`;
    a.click();
    URL.revokeObjectURL(a.href);
    setOpen(false);
  };
  const print = () => {
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(buildReportHtml(report));
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3.5 py-2 text-[13.5px] font-medium text-fg shadow-card hover:border-line-strong hover:bg-surface-2"
      >
        <FileText className="size-4" /> Report <ChevronDown className="size-3.5 text-faint" />
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-1.5 w-56 overflow-hidden rounded-lg border border-line bg-surface p-1 shadow-xl">
          <button onClick={download} className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[13.5px] hover:bg-surface-2">
            <FileDown className="size-4 text-brand" /> Download HTML report
          </button>
          <button onClick={print} className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[13.5px] hover:bg-surface-2">
            <Printer className="size-4 text-brand" /> Print / save as PDF
          </button>
        </div>
      )}
    </div>
  );
}
