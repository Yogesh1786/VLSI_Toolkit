import { useState } from "react";
import { BookOpen, Bug, Code, ListChecks } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { ReportButton, type Report } from "../components/ReportButton";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import {
  Alert,
  Card,
  Chips,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Select,
  StatusBadge,
  Tabs,
  Toggle,
} from "../components/ui";
import { downloadText, toCSV } from "../lib/format";

type Issue = {
  file: string;
  line: number;
  severity: "ERROR" | "WARNING" | "INFO";
  rule: string;
  message: string;
  source?: "lint" | "compiler";
};

const RULE_HELP: Record<string, string> = {
  MULTI_DRIVER:
    "The same signal is driven from more than one always/assign. In silicon this is a short circuit or X.",
  BLOCKING_IN_SEQ:
    "'=' inside a clocked block can create simulation/synthesis mismatches. Use '<=' for flops.",
  NONBLOCKING_IN_COMB:
    "'<=' in combinational logic delays updates in simulation. Use '='.",
  LATCH_RISK:
    "A signal keeps its old value on some path, so synthesis builds a latch. Give every signal a default value first.",
  CASE_NO_DEFAULT:
    "Uncovered case values can create latches or hide X values. Add 'default:'.",
  SENS_LIST:
    "A hand-written sensitivity list can miss signals. Use @(*) or always_comb.",
  CASEX:
    "casex treats X as don't-care and can hide bugs. Prefer casez or 'unique case'.",
  INITIAL_IN_RTL: "initial blocks are ignored by ASIC synthesis.",
  DELAY_IN_RTL:
    "#delays are ignored by synthesis; behaviour will differ from simulation.",
  CDC_UNSYNC:
    "A signal from another clock domain feeds logic directly. Its value can be caught mid-change (metastability): random failures in silicon.",
  CDC_SINGLE_FLOP:
    "A clock-domain crossing through one flip-flop is not enough. Use two flops in a row (a 2-flop synchronizer).",
  CDC_MULTIBIT:
    "Each bit of a bus can be synchronized on a different cycle, giving a corrupt value. Use Gray code, a req/ack handshake or an async FIFO.",
  RDC_UNSYNC:
    "A flop reset by one asynchronous reset feeds a flop that is not reset by it. When only the first reset is asserted, the second can capture a changing value (metastability).",
};

export default function Lint() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("findings");
  const [sev, setSev] = useState<Issue["severity"][]>([
    "ERROR",
    "WARNING",
    "INFO",
  ]);
  const [srcFile, setSrcFile] = useState("");
  const [compiler, setCompiler] = useState(true);
  const { data, loading, error } = useAnalysis<{
    issues: Issue[];
    rules: Record<string, string>;
    rule_help?: Record<string, string>;
    compiler?: { available: boolean; ran: boolean; top_modules: string[] };
  }>("/api/rtl/lint", files ? { files, compiler } : null);
  const ruleHelp = { ...RULE_HELP, ...(data?.rule_help ?? {}) };

  const issues = data?.issues ?? [];
  const count = (s: string) => issues.filter((i) => i.severity === s).length;
  const dirty = new Set(
    issues.filter((i) => i.severity !== "INFO").map((i) => i.file),
  ).size;
  const viewFile =
    files?.find((f) => f.name === srcFile) ??
    files?.find((f) => issues.some((i) => i.file === f.name)) ??
    files?.[0];

  const report: Report | null = data && files ? {
    tool: "RTL Lint",
    title: files.length === 1 ? files[0].name : `${files.length} RTL files`,
    files: files.map((f) => f.name),
    verdict: count("ERROR") ? { tone: "bad", text: `${count("ERROR")} error(s) must be fixed` } : count("WARNING") ? { tone: "warn", text: `No errors, ${count("WARNING")} warning(s) to review` } : { tone: "good", text: "Clean: no errors or warnings" },
    kpis: [
      { label: "Errors", value: count("ERROR"), tone: count("ERROR") ? "bad" : "good" },
      { label: "Warnings", value: count("WARNING"), tone: count("WARNING") ? "warn" : "good" },
      { label: "Info", value: count("INFO") },
      { label: "Files", value: files.length },
    ],
    sections: [{ title: "Findings", kind: "table", columns: [
      { key: "severity", label: "Severity" }, { key: "rule", label: "Rule" }, { key: "file", label: "File" },
      { key: "line", label: "Line", align: "right" }, { key: "message", label: "Message" }], rows: issues }],
  } : null;

  return (
    <>
      <PageHeader actions={<ReportButton report={report} />}
        area="RTL design"
        title="RTL Lint"
        icon={ListChecks}
        description={
          <>
            Check RTL for classic coding bugs before simulation. The example{" "}
            <code className="font-mono text-[13px]">lint_demo.v</code> has four
            planted bugs and{" "}
            <code className="font-mono text-[13px]">cdc_demo.v</code> three
            clock-domain-crossing bugs and{" "}
            <code className="font-mono text-[13px]">rdc_demo.v</code> a
            reset-domain crossing. With compiler checks on, every file is also
            compiled by slang, a full SystemVerilog front end: syntax and type
            errors, width truncation, undriven and unused signals.
          </>
        }
      />
      <Card className="mb-6">
        <FileSource
          label="RTL files"
          multiple
          examples={[
            "lint_demo.v",
            "cdc_demo.v",
            "rdc_demo.v",
            "counter.v",
            "fifo.v",
            "alu.v",
          ]}
          accept=".v,.sv,.vh,.svh"
          onChange={setFiles}
        />
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4 text-[13px] text-muted">
          <Toggle checked={compiler} onChange={setCompiler} label="Compiler checks (slang)" />
          {data?.compiler && !data.compiler.available && <span className="text-warn">slang is not installed on this server (pip install pyslang)</span>}
          {data?.compiler?.ran && data.compiler.top_modules.length > 0 && (
            <span>Elaborated top module{data.compiler.top_modules.length > 1 ? "s" : ""}: <b className="font-mono text-fg">{data.compiler.top_modules.join(", ")}</b></span>
          )}
        </div>
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!files ? (
        <EmptyState
          icon={ListChecks}
          title="No files yet"
          text="Upload one or more Verilog/SystemVerilog files."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : (
        data && (
          <>
            <KpiGrid
              items={[
                {
                  label: "Files checked",
                  value: files.length,
                  note: `${files.length - dirty} clean`,
                  tone: dirty ? "neutral" : "good",
                },
                {
                  label: "Errors",
                  value: count("ERROR"),
                  note: count("ERROR") ? "must fix" : "none",
                  tone: count("ERROR") ? "bad" : "good",
                },
                {
                  label: "Warnings",
                  value: count("WARNING"),
                  note: count("WARNING") ? "review" : "none",
                  tone: count("WARNING") ? "warn" : "good",
                },
                {
                  label: "Info",
                  value: count("INFO"),
                  note: "style hints",
                  tone: "info",
                },
                {
                  label: "Rules checked",
                  value: Object.keys(data.rules).length,
                  note: "see Rule reference",
                },
              ]}
            />
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                {
                  id: "findings",
                  label: "Findings",
                  icon: Bug,
                  count: issues.length,
                },
                { id: "source", label: "Source viewer", icon: Code },
                { id: "rules", label: "Rule reference", icon: BookOpen },
              ]}
            />
            {tab === "findings" &&
              (issues.length === 0 ? (
                <Alert tone="good" title="No issues found">
                  All files passed every rule.
                </Alert>
              ) : (
                <Card bodyClass="p-4">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <Chips
                      selected={sev}
                      onChange={setSev}
                      options={[
                        {
                          value: "ERROR",
                          label: "Errors",
                          tone: "bad",
                          count: count("ERROR"),
                        },
                        {
                          value: "WARNING",
                          label: "Warnings",
                          tone: "warn",
                          count: count("WARNING"),
                        },
                        {
                          value: "INFO",
                          label: "Info",
                          tone: "info",
                          count: count("INFO"),
                        },
                      ]}
                    />
                    <button
                      className="text-[13px] font-medium text-brand hover:underline"
                      onClick={() =>
                        downloadText(
                          "lint_findings.csv",
                          toCSV(issues),
                          "text/csv",
                        )
                      }
                    >
                      Export CSV
                    </button>
                  </div>
                  <DataTable
                    rows={issues.filter((i) => sev.includes(i.severity))}
                    searchable
                    columns={[
                      {
                        key: "severity",
                        header: "Severity",
                        render: (i) => <StatusBadge status={i.severity} />,
                        value: (i) =>
                          ({ ERROR: 0, WARNING: 1, INFO: 2 })[i.severity],
                      },
                      { key: "rule", header: "Rule", mono: true, render: (i: Issue) => (
                      <span>{i.rule}{i.source === "compiler" && <span className="ml-1.5 rounded bg-brand-soft px-1.5 font-sans text-[10.5px] font-semibold text-brand">slang</span>}</span>) },
                      {
                        key: "file",
                        header: "File",
                        render: (i) => (
                          <button
                            className="font-mono text-[12.5px] text-brand hover:underline"
                            onClick={() => {
                              setSrcFile(i.file);
                              setTab("source");
                            }}
                          >
                            {i.file}:{i.line}
                          </button>
                        ),
                        value: (i) =>
                          `${i.file}:${String(i.line).padStart(6, "0")}`,
                      },
                      { key: "message", header: "Message", wrap: true },
                    ]}
                  />
                </Card>
              ))}
            {tab === "source" && viewFile && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="w-64">
                    <Select
                      value={viewFile.name}
                      onChange={setSrcFile}
                      options={files.map((f) => ({
                        value: f.name,
                        label: `${f.name}  (${issues.filter((i) => i.file === f.name).length} findings)`,
                      }))}
                    />
                  </div>
                  <span className="text-[13px] text-muted">
                    Highlighted lines have findings.
                  </span>
                </div>
                {issues
                  .filter((i) => i.file === viewFile.name)
                  .map((i) => (
                    <div
                      key={`${i.line}${i.rule}`}
                      className="flex items-center gap-3 text-[13px]"
                    >
                      <StatusBadge status={i.severity} />
                      <span className="font-mono text-muted">
                        line {i.line}
                      </span>
                      <span>{i.message}</span>
                    </div>
                  ))}
                <CodeBlock
                  code={viewFile.text}
                  lang="verilog"
                  filename={viewFile.name}
                  highlightLines={issues
                    .filter((i) => i.file === viewFile.name)
                    .map((i) => i.line)}
                />
              </div>
            )}
            {tab === "rules" && (
              <Card bodyClass="p-4">
                <DataTable
                  rows={Object.entries(ruleHelp).map(([rule, why]) => ({
                    rule,
                    why,
                    severity: data.rules[rule] ?? "INFO",
                  }))}
                  columns={[
                    {
                      key: "severity",
                      header: "Severity",
                      render: (r) => <StatusBadge status={r.severity} />,
                    },
                    { key: "rule", header: "Rule", mono: true },
                    { key: "why", header: "Why it matters", wrap: true },
                  ]}
                />
              </Card>
            )}
          </>
        )
      )}
    </>
  );
}
