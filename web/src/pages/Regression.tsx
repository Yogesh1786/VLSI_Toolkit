import { useEffect, useState } from "react";
import { ClipboardCheck, Download, FileText, List, Network } from "lucide-react";
import { getJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import {
  Alert, Button, Card, Chips, EmptyState, KpiGrid, LoadingBlock, PageHeader, Select, StackedBar, StatusBadge, Tabs,
} from "../components/ui";
import { downloadText, pct, TONE_HEX, toCSV } from "../lib/format";

type TestResult = {
  file: string; test: string; seed: string; status: "PASS" | "FAIL" | "INCOMPLETE"; errors: number; fatals: number;
  warnings: number; first_error: string; short_error: string; signature: string;
};
type Result = { results: TestResult[]; signatures: { signature: string; count: number; status: string; tests: string[] }[]; html_report: string };

export default function Regression() {
  const [examples, setExamples] = useState<string[]>([]);
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("sig");
  const [show, setShow] = useState<TestResult["status"][]>(["FAIL", "INCOMPLETE", "PASS"]);
  const [log, setLog] = useState("");
  useEffect(() => { getJSON<string[]>("/api/examples?folder=regression_logs").then(setExamples).catch(() => setExamples([])); }, []);
  const { data, loading, error } = useAnalysis<Result>("/api/verif/regress", files ? { files } : null);

  const results = data?.results ?? [];
  const n = results.length || 1;
  const count = (s: string) => results.filter((r) => r.status === s).length;
  const rate = count("PASS") / n;
  const sorted = [...results].sort((a, b) => Number(a.status === "PASS") - Number(b.status === "PASS") || a.test.localeCompare(b.test));
  const logFile = files?.find((f) => f.name === log) ?? files?.find((f) => f.name === sorted[0]?.file);
  const errorLines = (logFile?.text ?? "").split("\n").map((l, i) => ({ l, i: i + 1 }))
    .filter(({ l }) => /ERROR|Error|FATAL|Fatal|\*E,|\*F,/.test(l) && !/^\s*UVM_(ERROR|FATAL)\s*:/.test(l));

  return (
    <>
      <PageHeader area="Verification" title="Regression Triage" icon={ClipboardCheck}
        description={<>The status of every test, with failures grouped by <i>signature</i>, so 50 failing tests can be seen as the 2 bugs they really are.</>}
        actions={data ? <Button icon={Download} onClick={() => downloadText("regression.html", data.html_report, "text/html")}>HTML report</Button> : undefined} />
      <Card className="mb-6">
        {examples.length > 0 && <FileSource label="Simulation logs" multiple examples={examples} accept=".log,.txt,.out" onChange={setFiles} />}
      </Card>

      {error && <Alert tone="bad" title="Request failed">{error}</Alert>}
      {!files ? <EmptyState icon={ClipboardCheck} title="No logs yet" text="Upload the log files of a regression run (UVM, VCS, Questa, Xcelium, Icarus)." />
        : loading && !data ? <LoadingBlock /> : data && (
          <>
            <KpiGrid items={[
              { label: "Tests", value: results.length },
              { label: "Pass rate", value: pct(rate), note: rate === 1 ? "all passing" : "needs attention", tone: rate === 1 ? "good" : "bad" },
              { label: "Failed", value: count("FAIL"), note: count("FAIL") ? "errors or fatals" : "none", tone: count("FAIL") ? "bad" : "good" },
              { label: "Incomplete", value: count("INCOMPLETE"), note: count("INCOMPLETE") ? "crash / timeout" : "none",
                tone: count("INCOMPLETE") ? "warn" : "good", hint: "No end-of-simulation marker was found in the log" },
              { label: "Unique failures", value: data.signatures.length, note: "distinct signatures" },
            ]} />
            <Card className="mb-6" bodyClass="px-5 py-4">
              <StackedBar parts={[
                { label: "Pass", value: count("PASS"), color: TONE_HEX.good },
                { label: "Fail", value: count("FAIL"), color: TONE_HEX.bad },
                { label: "Incomplete", value: count("INCOMPLETE"), color: TONE_HEX.warn },
              ]} />
            </Card>
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "sig", label: "Failure signatures", icon: Network, count: data.signatures.length },
              { id: "all", label: "All tests", icon: List, count: results.length },
              { id: "log", label: "Log viewer", icon: FileText },
            ]} />
            {tab === "sig" && (data.signatures.length === 0 ? <Alert tone="good" title="Every test passed" /> : (
              <div className="space-y-3">
                <p className="text-[13.5px] text-muted">Debug the biggest group first: these tests most likely hit the same bug.</p>
                {data.signatures.map((s, i) => (
                  <Card key={i} bodyClass="flex flex-wrap items-start gap-4 p-4">
                    <div className="grid size-12 shrink-0 place-items-center rounded-xl bg-surface-3 text-center">
                      <div className="text-[18px] leading-none font-bold">{s.count}</div><div className="text-[10px] text-faint">tests</div>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1.5 flex items-center gap-2"><StatusBadge status={s.status} /><span className="text-[12px] text-faint">signature #{i + 1}</span></div>
                      <div className="font-mono text-[13px] break-words">{s.signature}</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {s.tests.map((t) => <span key={t} className="rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[12px] text-muted">{t}</span>)}
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            ))}
            {tab === "all" && (
              <Card bodyClass="p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <Chips selected={show} onChange={setShow} options={[
                    { value: "FAIL", label: "Fail", tone: "bad", count: count("FAIL") },
                    { value: "INCOMPLETE", label: "Incomplete", tone: "warn", count: count("INCOMPLETE") },
                    { value: "PASS", label: "Pass", tone: "good", count: count("PASS") },
                  ]} />
                  <button className="text-[13px] font-medium text-brand hover:underline"
                    onClick={() => downloadText("regression.csv", toCSV(results), "text/csv")}>Export CSV</button>
                </div>
                <DataTable rows={sorted.filter((r) => show.includes(r.status))} searchable columns={[
                  { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
                  { key: "test", header: "Test", mono: true },
                  { key: "seed", header: "Seed", mono: true, render: (r) => r.seed || "–" },
                  { key: "errors", header: "Err", align: "right" },
                  { key: "fatals", header: "Fatal", align: "right" },
                  { key: "warnings", header: "Warn", align: "right" },
                  { key: "short_error", header: "First error", wrap: true, render: (r) => <span className="text-[13px]">{r.short_error || "–"}</span> },
                  { key: "file", header: "Log", render: (r) => (
                    <button className="font-mono text-[12.5px] text-brand hover:underline" onClick={() => { setLog(r.file); setTab("log"); }}>{r.file}</button>) },
                ]} />
              </Card>
            )}
            {tab === "log" && logFile && (
              <div className="space-y-4">
                <div className="w-full max-w-md">
                  <Select value={logFile.name} onChange={setLog}
                    options={sorted.map((r) => ({ value: r.file, label: `${r.status.padEnd(11, " ")} ${r.file}` }))} />
                </div>
                {errorLines.length > 0 && (
                  <Card title="Error lines" subtitle={`${errorLines.length} found`} bodyClass="p-0">
                    <div className="divide-y divide-line font-mono text-[12.5px]">
                      {errorLines.map(({ l, i }) => (
                        <div key={i} className="flex gap-4 px-4 py-2"><span className="text-faint tabular-nums">{i}</span><span className="break-all text-bad">{l}</span></div>
                      ))}
                    </div>
                  </Card>
                )}
                <CodeBlock code={logFile.text} filename={logFile.name} highlightLines={errorLines.map((e) => e.i)} maxHeight={480} />
              </div>
            )}
          </>
        )}
    </>
  );
}
