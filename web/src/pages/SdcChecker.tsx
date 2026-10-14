import { useState } from "react";
import { BookOpen, Bug, Clock, Code, FileCheck2 } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import { Alert, Badge, Card, Chips, EmptyState, KpiGrid, LoadingBlock, PageHeader, StatusBadge, Tabs, Toggle } from "../components/ui";
import { downloadText, toCSV } from "../lib/format";

type Severity = "ERROR" | "WARNING" | "INFO";
type Issue = { rule: string; severity: Severity; line: number; message: string };
type ClockDef = {
  name: string; period: number | null; freq_mhz: number | null; ports: string[]; generated: boolean; master: string | null;
  uncertainty: boolean; line: number; divide_by?: number | null; multiply_by?: number | null;
};
type Result = {
  clocks: ClockDef[]; issues: Issue[]; counts: Record<Severity, number>; rtl_checked: boolean; rtl_top: string | null;
  io_delays: { kind: string; clock: string | null; value: number | null; ports: string[]; line: number }[];
  exceptions: { kind: string; line: number; text: string }[];
  rules: { rule: string; severity: Severity; description: string }[];
};

export default function SdcChecker() {
  const [sdc, setSdc] = useState<SourceFile[] | null>(null);
  const [rtl, setRtl] = useState<SourceFile[] | null>(null);
  const [useRtl, setUseRtl] = useState(true);
  const [example, setExample] = useState("signoff/uart_top.sdc");
  const [tab, setTab] = useState("issues");
  const [sev, setSev] = useState<Severity[]>(["ERROR", "WARNING", "INFO"]);
  const file = sdc?.[0] ?? null;
  const body = file ? { ...file, rtl: useRtl && rtl ? rtl : [] } : null;
  const { data: r, loading, error } = useAnalysis<Result>("/api/pd/sdc", body);
  const issues = r?.issues ?? [];
  const help = Object.fromEntries((r?.rules ?? []).map((x) => [x.rule, x.description]));

  return (
    <>
      <PageHeader area="Physical design" title="SDC Checker" icon={FileCheck2}
        description={<>Check timing constraints for the mistakes that make STA silently wrong: unknown clocks or ports, missing I/O delays, multicycle paths without hold, over-broad false paths. The example <code className="font-mono text-[13px]">uart_top.sdc</code> has planted mistakes; <code className="font-mono text-[13px]">uart_top_fixed.sdc</code> is clean.</>} />
      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Card title="Constraints (SDC)">
          <div className="mb-4 flex flex-wrap gap-2">
            {["signoff/uart_top.sdc", "signoff/uart_top_fixed.sdc"].map((e) => (
              <button key={e} onClick={() => setExample(e)}
                className={`rounded-md border px-2.5 py-1 font-mono text-[12px] ${example === e ? "border-brand text-brand" : "border-line text-muted hover:text-fg"}`}>
                {e.split("/")[1]}</button>
            ))}
          </div>
          <FileSource label="SDC file" examples={[example]} accept=".sdc,.tcl,.xdc" wsKinds={["sdc"]} onChange={setSdc} />
        </Card>
        <Card title="Top-level RTL (optional)" actions={<Toggle checked={useRtl} onChange={setUseRtl} label="Check against RTL" />}>
          {useRtl
            ? <FileSource label="Top module" examples={["rtl_project/uart_top.v"]} accept=".v,.sv" wsKinds={["rtl"]} onChange={setRtl} />
            : <p className="text-[13px] text-muted">With the RTL top module the checker also finds misspelled port names and inputs/outputs that have no I/O delay.</p>}
        </Card>
      </div>

      {error && <Alert tone="bad" title="Request failed">{error}</Alert>}
      {!file ? <EmptyState icon={FileCheck2} title="No constraints yet" text="Upload an .sdc file (and optionally the top-level Verilog)." />
        : loading && !r ? <LoadingBlock /> : r && (
          <>
            <KpiGrid items={[
              { label: "Errors", value: r.counts.ERROR, note: r.counts.ERROR ? "constraints ignored or wrong" : "none", tone: r.counts.ERROR ? "bad" : "good" },
              { label: "Warnings", value: r.counts.WARNING, note: r.counts.WARNING ? "review" : "none", tone: r.counts.WARNING ? "warn" : "good" },
              { label: "Clocks", value: r.clocks.length, note: r.clocks.map((c) => c.name).join(", ") || "none defined", tone: r.clocks.length ? "info" : "bad" },
              { label: "I/O delays · exceptions", value: `${r.io_delays.length} · ${r.exceptions.length}`,
                note: r.rtl_checked ? `checked against ${r.rtl_top}` : "RTL not checked" },
            ]} />
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "issues", label: "Findings", icon: Bug, count: issues.length },
              { id: "clocks", label: "Clocks", icon: Clock, count: r.clocks.length },
              { id: "source", label: "Source", icon: Code },
              { id: "rules", label: "Rule reference", icon: BookOpen },
            ]} />
            {tab === "issues" && (issues.length === 0 ? <Alert tone="good" title="No issues found">Every check passed{r.rtl_checked ? ", including the port and I/O-coverage checks against the RTL" : ""}.</Alert> : (
              <Card bodyClass="p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <Chips selected={sev} onChange={setSev} options={[
                    { value: "ERROR", label: "Errors", tone: "bad", count: r.counts.ERROR },
                    { value: "WARNING", label: "Warnings", tone: "warn", count: r.counts.WARNING },
                    { value: "INFO", label: "Info", tone: "info", count: r.counts.INFO },
                  ]} />
                  <button className="text-[13px] font-medium text-brand hover:underline"
                    onClick={() => downloadText("sdc_findings.csv", toCSV(issues), "text/csv")}>Export CSV</button>
                </div>
                <DataTable rows={issues.filter((i) => sev.includes(i.severity))} searchable columns={[
                  { key: "severity", header: "Severity", render: (i) => <StatusBadge status={i.severity} />,
                    value: (i) => ({ ERROR: 0, WARNING: 1, INFO: 2 })[i.severity] },
                  { key: "rule", header: "Rule", mono: true },
                  { key: "line", header: "Line", align: "right", render: (i) => (i.line ? (
                    <button className="font-mono text-brand hover:underline" onClick={() => setTab("source")}>{i.line}</button>) : "–") },
                  { key: "message", header: "Message", wrap: true, render: (i) => (
                    <div><div>{i.message}</div><div className="mt-0.5 text-[12px] text-faint">{help[i.rule]}</div></div>) },
                ]} />
              </Card>
            ))}
            {tab === "clocks" && (r.clocks.length === 0 ? <Alert tone="bad" title="No clocks defined">Add create_clock for every clock input.</Alert> : (
              <Card bodyClass="p-4">
                <DataTable rows={r.clocks} columns={[
                  { key: "name", header: "Clock", mono: true },
                  { key: "kind", header: "Kind", render: (c) => (c.generated
                    ? <Badge tone="info">generated from {c.master ?? "?"}{c.divide_by ? ` ÷${c.divide_by}` : ""}{c.multiply_by ? ` ×${c.multiply_by}` : ""}</Badge>
                    : <Badge>primary</Badge>) },
                  { key: "period", header: "Period (ns)", align: "right", render: (c) => c.period ?? "?" },
                  { key: "freq_mhz", header: "Frequency (MHz)", align: "right", render: (c) => c.freq_mhz ?? "?" },
                  { key: "ports", header: "Source", mono: true, render: (c) => c.ports.join(" ") || "–" },
                  { key: "uncertainty", header: "Uncertainty", render: (c) => <StatusBadge status={c.uncertainty ? "PASS" : c.generated ? "INFO" : "WARNING"} /> },
                  { key: "line", header: "Line", align: "right" },
                ]} />
              </Card>
            ))}
            {tab === "source" && (
              <CodeBlock code={file.text} filename={file.name} highlightLines={issues.map((i) => i.line).filter(Boolean)} />
            )}
            {tab === "rules" && (
              <Card bodyClass="p-4">
                <DataTable rows={r.rules} columns={[
                  { key: "severity", header: "Severity", render: (x) => <StatusBadge status={x.severity} /> },
                  { key: "rule", header: "Rule", mono: true },
                  { key: "description", header: "Why it matters", wrap: true },
                ]} />
              </Card>
            )}
          </>
        )}
    </>
  );
}
