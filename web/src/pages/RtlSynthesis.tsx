import { useEffect, useState } from "react";
import { Boxes, Cog, FileCode, Layers, ListChecks, TriangleAlert } from "lucide-react";
import { getJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { ReportButton, type Report } from "../components/ReportButton";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import { Alert, BarList, Card, EmptyState, Field, KpiGrid, LoadingBlock, PageHeader, Select, Tabs, Toggle } from "../components/ui";
import { fmtInt } from "../lib/format";

type ModuleRow = {
  name: string; parameterized: boolean; cells: number; seq: number; comb: number; latches: number; memories: number;
  nand2_eq: number; submodules: Record<string, number>; cell_types: { cell: string; count: number }[];
};
type Result = {
  top: string; modules: ModuleRow[]; logic_depth: number | null; warnings: string[]; latches: string[]; black_boxes: string[];
  totals: { cells: number; seq: number; comb: number; latches: number; nand2_eq: number };
  netlist: string; engine: string; abc: boolean; flatten: boolean; seconds: number;
};

/** "$_DFFE_PN0P_" -> "DFFE_PN0P"; plain-language names for the common gates. */
const CELL_NAMES: Record<string, string> = {
  $_NOT_: "NOT (inverter)", $_AND_: "AND2", $_OR_: "OR2", $_XOR_: "XOR2", $_XNOR_: "XNOR2", $_NAND_: "NAND2", $_NOR_: "NOR2",
  $_MUX_: "MUX2", $_ANDNOT_: "AND2 with inverted input", $_ORNOT_: "OR2 with inverted input", $_AOI3_: "AOI21", $_OAI3_: "OAI21",
};
const cellLabel = (c: string) => CELL_NAMES[c] ?? c.replace(/^\$_|_$/g, "");

export default function RtlSynthesis() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [examples, setExamples] = useState<string[]>([]);
  const [top, setTop] = useState("");
  const [flatten, setFlatten] = useState(false);
  const [tab, setTab] = useState("modules");
  const [selected, setSelected] = useState("");

  useEffect(() => {
    getJSON<string[]>("/api/examples?folder=rtl_project").then(setExamples).catch(() => setExamples([]));
  }, []);
  // module names for the top-module picker (fast regex parser, not Yosys)
  const { data: hier } = useAnalysis<{ modules: { name: string }[]; main_top: string | null }>("/api/rtl/hierarchy", files ? { files } : null);
  useEffect(() => setTop(""), [files]);
  const { data, loading, error } = useAnalysis<Result>("/api/rtl/synth", files ? { files, top: top || null, flatten } : null, 400);
  const shownModule = data?.modules.find((m) => m.name === selected) ?? data?.modules[0];

  const report: Report | null = data && files ? {
    tool: "RTL Synthesis (Yosys)",
    title: `Top ${data.top}`,
    files: files.map((f) => f.name),
    verdict: data.totals.latches ? { tone: "bad", text: `${data.totals.latches} latch(es) inferred` } : { tone: "good", text: "Synthesized without latches" },
    kpis: [
      { label: "Cells", value: data.totals.cells }, { label: "Flip-flops", value: data.totals.seq },
      { label: "NAND2 equivalents", value: Math.round(data.totals.nand2_eq) }, { label: "Logic depth", value: data.logic_depth ?? "–" },
      { label: "Latches", value: data.totals.latches, tone: data.totals.latches ? "bad" : "good" },
    ],
    sections: [
      { title: "Modules", kind: "table", columns: [{ key: "name", label: "Module" }, { key: "cells", label: "Cells", align: "right" }, { key: "seq", label: "Flip-flops", align: "right" }, { key: "comb", label: "Gates", align: "right" }, { key: "nand2_eq", label: "NAND2 eq.", align: "right" }, { key: "latches", label: "Latches", align: "right" }], rows: data.modules },
      ...(data.black_boxes.length ? [{ title: "Black boxes", kind: "list" as const, items: data.black_boxes }] : []),
      ...(data.warnings.length ? [{ title: "Yosys warnings", kind: "list" as const, items: data.warnings }] : []),
    ],
  } : null;

  return (
    <>
      <PageHeader actions={<ReportButton report={report} />} area="RTL design" title="RTL Synthesis" icon={Cog}
        description="Real logic synthesis with Yosys, running on the server: gate count, flip-flops, NAND2-equivalent size, logic depth, inferred latches and black boxes, and the gate-level netlist. No EDA license needed." />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          {examples.length > 0 && (
            <FileSource label="RTL files" multiple examples={examples} accept=".v,.sv,.vh,.svh" wsKinds={["rtl"]} onChange={setFiles} />
          )}
          <div className="flex flex-wrap items-end gap-4 lg:flex-col lg:items-stretch">
            <Field label="Top module" className="w-56">
              <Select value={top} onChange={setTop} options={[
                { value: "", label: `Automatic${hier?.main_top ? ` (${hier.main_top})` : ""}` },
                ...(hier?.modules ?? []).map((m) => ({ value: m.name, label: m.name })),
              ]} />
            </Field>
            <Toggle checked={flatten} onChange={setFlatten} label="Flatten hierarchy" />
          </div>
        </div>
      </Card>

      {error && <Alert tone="bad" title="Synthesis failed">{error}</Alert>}
      {!files ? <EmptyState icon={Cog} title="No RTL yet" text="Pick the example UART project or upload your Verilog/SystemVerilog files." />
        : loading && !data ? <LoadingBlock label="Synthesizing with Yosys… (the first run on the server can take a few seconds)" />
        : data && (
          <>
            <KpiGrid items={[
              { label: "Cells", value: fmtInt(data.totals.cells), note: `top: ${data.top}`, tone: "info",
                hint: "Generic gates and flip-flops after synthesis, counting every instance of every module." },
              { label: "Flip-flops", value: fmtInt(data.totals.seq), note: `${data.totals.cells ? Math.round((data.totals.seq / data.totals.cells) * 100) : 0}% of cells` },
              { label: "NAND2 equivalents", value: fmtInt(Math.round(data.totals.nand2_eq)), note: "library-independent size",
                hint: "A rough size estimate: each gate counted as its equivalent number of 2-input NAND gates (a flip-flop ≈ 4.5)." },
              { label: "Logic depth", value: data.logic_depth ?? "–", note: "levels, longest path",
                hint: "Gates on the longest combinational path between registers/ports. Deeper logic usually means a slower clock." },
              { label: "Latches", value: data.totals.latches, note: data.totals.latches ? "check your RTL" : "none inferred",
                tone: data.totals.latches ? "bad" : "good" },
            ]} />

            {data.latches.length > 0 && (
              <Alert tone="bad" title={`${data.latches.length} latch${data.latches.length > 1 ? "es" : ""} inferred`}>
                {data.latches.join(", ")}: a signal keeps its old value on some path through combinational logic. Give it a default value
                or cover every case. RTL Lint shows the exact lines.
              </Alert>
            )}
            {data.black_boxes.length > 0 && (
              <Alert tone="info" title="Black boxes">
                {data.black_boxes.join(", ")}: instantiated but not defined (memories, IP or library cells). They are kept as empty boxes and not counted.
              </Alert>
            )}
            {!data.abc && (
              <Alert tone="warn" title="Technology mapping (ABC) was skipped">
                The counts come from Yosys's generic gates before ABC optimization, so they are somewhat higher than a full flow would give.
              </Alert>
            )}

            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "modules", label: "Modules", icon: Layers, count: data.modules.length },
              { id: "cells", label: "Cell types", icon: Boxes },
              { id: "warnings", label: "Warnings", icon: TriangleAlert, count: data.warnings.length },
              { id: "netlist", label: "Gate-level netlist", icon: FileCode },
            ]} />
            {tab === "modules" && (
              <Card bodyClass="p-4">
                <DataTable rows={data.modules} initialSort={{ key: "nand2_eq", dir: "desc" }} columns={[
                  { key: "name", header: "Module", mono: true, render: (m) => (
                    <span>{m.name}{m.name === data.top && <span className="ml-2 rounded bg-brand-soft px-1.5 font-sans text-[11px] font-semibold text-brand">top</span>}
                      {m.parameterized && <span className="ml-2 font-sans text-[11px] text-faint">parameterized</span>}</span>) },
                  { key: "cells", header: "Cells", align: "right" },
                  { key: "seq", header: "Flip-flops", align: "right" },
                  { key: "comb", header: "Gates", align: "right" },
                  { key: "nand2_eq", header: "NAND2 eq.", align: "right", render: (m) => fmtInt(Math.round(m.nand2_eq)) },
                  { key: "latches", header: "Latches", align: "right", render: (m) => m.latches ? <span className="font-semibold text-bad">{m.latches}</span> : 0 },
                  { key: "submodules", header: "Instances", wrap: true, value: (m) => Object.keys(m.submodules).join(" "),
                    render: (m) => Object.entries(m.submodules).map(([k, v]) => `${k}${v > 1 ? ` ×${v}` : ""}`).join(", ") || "–" },
                ]} />
                <p className="mt-3 text-[12.5px] text-muted">Counts per module exclude the modules it instantiates; the totals above include every instance.</p>
              </Card>
            )}
            {tab === "cells" && shownModule && (
              <Card title="Cell usage" subtitle="Generic Yosys cells in one module"
                actions={data.modules.length > 1 ? <div className="w-56"><Select value={shownModule.name} onChange={setSelected}
                  options={data.modules.map((m) => ({ value: m.name, label: m.name }))} /></div> : undefined}>
                <BarList items={shownModule.cell_types.map((c) => ({ label: cellLabel(c.cell), value: c.count }))} />
              </Card>
            )}
            {tab === "warnings" && (data.warnings.length === 0 ? <Alert tone="good" title="No warnings from Yosys" /> : (
              <Card bodyClass="p-4">
                <ul className="space-y-2 text-[13.5px]">
                  {data.warnings.map((w) => (
                    <li key={w} className="flex gap-2"><ListChecks className="mt-0.5 size-4 shrink-0 text-warn" /><span className="font-mono text-[12.5px]">{w}</span></li>
                  ))}
                </ul>
              </Card>
            ))}
            {tab === "netlist" && (
              <CodeBlock code={data.netlist} lang="verilog" filename={`${data.top}_netlist.v`} />
            )}
            <p className="mt-4 text-[12.5px] text-faint">
              Yosys ({data.engine === "wasm" ? "WebAssembly build" : "native"}) · {data.flatten ? "flattened" : "hierarchical"} · {data.seconds} s
            </p>
          </>
        )}
    </>
  );
}
