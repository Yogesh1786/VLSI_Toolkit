import { useState } from "react";
import { Download, Layers, Network, Zap } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { Alert, BarList, Button, Card, EmptyState, KpiGrid, LoadingBlock, PageHeader, StackedBar, Tabs, type KpiItem } from "../components/ui";
import { downloadText, PALETTE, toCSV } from "../lib/format";

type Totals = { internal: number | null; switching: number | null; dynamic: number | null; leakage: number | null; total: number | null };
type Group = { group: string; internal: number; switching: number; leakage: number; total: number };
type Hier = { name: string; design: string; depth: number; switching: number; internal: number; leakage: number; total: number; percent: number };
type Report = { design: string | null; unit: string; totals: Totals; groups: Group[]; hierarchy: Hier[] };

/** mW value with a unit that keeps 3-4 significant digits (µW for small numbers). */
function power(v: number | null | undefined) {
  if (v == null) return "–";
  if (v === 0) return "0";
  return Math.abs(v) < 0.1 ? `${(v * 1000).toFixed(2)} µW` : `${v.toFixed(4)} mW`;
}

const GROUP_HELP: Record<string, string> = {
  clock_network: "Clock tree buffers and clock pins of flops. Clock gating is the usual fix when this dominates.",
  register: "Flip-flops (internal power of the flop itself).",
  combinational: "Logic gates between registers.",
  sequential: "Latches and other sequential cells.",
  memory: "SRAM / register-file macros.",
  io_pad: "I/O pad cells.",
  black_box: "Blocks without a power model.",
};

export default function PowerReport() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("hier");
  const file = files?.[0] ?? null;
  const { data: r, loading, error } = useAnalysis<Report>("/api/pd/power", file);
  const t = r?.totals;
  const groups = (r?.groups ?? []).filter((g) => g.total > 0).sort((a, b) => b.total - a.total);
  const children = (r?.hierarchy ?? []).filter((h) => h.depth === 1);

  const kpis: KpiItem[] = t ? [
    { label: "Total power", value: power(t.total), note: r?.design ? `design ${r.design}` : undefined, tone: "info" },
    { label: "Dynamic", value: power(t.dynamic), note: t.total ? `${(((t.dynamic ?? 0) / t.total) * 100).toFixed(1)}% of total` : undefined,
      hint: "Internal (inside cells) + switching (charging net capacitance). Scales with frequency, activity and V²." },
    { label: "Leakage", value: power(t.leakage), note: t.total ? `${(((t.leakage ?? 0) / t.total) * 100).toFixed(1)}% of total` : undefined,
      hint: "Static power that flows even when nothing toggles. Grows with temperature and low-Vt cells." },
    { label: "Top consumer", value: children.length ? [...children].sort((a, b) => b.total - a.total)[0].name : groups[0]?.group ?? "–",
      note: children.length ? `${[...children].sort((a, b) => b.total - a.total)[0].percent.toFixed(1)}% of the design` : groups[0] ? power(groups[0].total) : undefined },
  ] : [];

  return (
    <>
      <PageHeader area="Physical design" title="Power Report" icon={Zap}
        description="Read report_power output from PrimePower, PrimeTime-PX, Design Compiler or Innovus: dynamic vs leakage, power groups and the power of each instance."
        actions={r?.hierarchy.length ? <Button icon={Download} onClick={() => downloadText("power_hierarchy.csv", toCSV(r.hierarchy), "text/csv")}>Export CSV</Button> : undefined} />
      <Card className="mb-6">
        <FileSource label="Power report" examples={["signoff/power.rpt"]} wsKinds={["power"]} onChange={setFiles} />
      </Card>

      {error && <Alert tone="bad" title="Could not read the report">{error}</Alert>}
      {!file ? <EmptyState icon={Zap} title="No report yet" text="Upload the output of report_power (optionally with -hierarchy)." />
        : loading && !r ? <LoadingBlock /> : r && t && (
          <>
            <KpiGrid items={kpis} />
            <Card title="Power split" subtitle="Values in µW" className="mb-6">
              <StackedBar parts={[
                { label: "Internal", value: Math.round((t.internal ?? 0) * 1000), color: PALETTE[0] },
                { label: "Switching", value: Math.round((t.switching ?? 0) * 1000), color: PALETTE[1] },
                { label: "Leakage", value: Math.round((t.leakage ?? 0) * 1000), color: PALETTE[3] },
              ]} />
            </Card>
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "hier", label: "By instance", icon: Network, count: r.hierarchy.length },
              { id: "groups", label: "Power groups", icon: Layers, count: groups.length },
            ]} />
            {tab === "hier" && (r.hierarchy.length === 0
              ? <Alert tone="info" title="No hierarchy table">Run report_power -hierarchy to see the power of each instance.</Alert> : (
              <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
                <Card title="Biggest consumers" subtitle="First-level instances">
                  <BarList items={[...children].sort((a, b) => b.total - a.total).map((h) => ({ label: `${h.name} (${h.design})`, value: h.total }))}
                    format={power} />
                </Card>
                <Card bodyClass="p-4">
                  <DataTable rows={r.hierarchy} columns={[
                    { key: "name", header: "Instance", render: (h) => (
                      <span className="font-mono text-[12.5px]" style={{ paddingLeft: h.depth * 16 }}>{h.name}</span>) },
                    { key: "design", header: "Design", mono: true },
                    { key: "switching", header: "Switching", align: "right", render: (h) => power(h.switching) },
                    { key: "internal", header: "Internal", align: "right", render: (h) => power(h.internal) },
                    { key: "leakage", header: "Leakage", align: "right", render: (h) => power(h.leakage) },
                    { key: "total", header: "Total", align: "right", render: (h) => <b>{power(h.total)}</b> },
                    { key: "percent", header: "%", align: "right", render: (h) => (
                      <div className="flex items-center justify-end gap-2"><div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-3">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, h.percent)}%` }} /></div>{h.percent.toFixed(1)}</div>) },
                  ]} />
                </Card>
              </div>
            ))}
            {tab === "groups" && (groups.length === 0 ? <Alert tone="info" title="No power-group table in this report" /> : (
              <Card bodyClass="p-4">
                <DataTable rows={groups} columns={[
                  { key: "group", header: "Group", mono: true },
                  { key: "internal", header: "Internal", align: "right", render: (g) => power(g.internal) },
                  { key: "switching", header: "Switching", align: "right", render: (g) => power(g.switching) },
                  { key: "leakage", header: "Leakage", align: "right", render: (g) => power(g.leakage) },
                  { key: "total", header: "Total", align: "right", render: (g) => <b>{power(g.total)}</b> },
                  { key: "share", header: "Share", align: "right", value: (g) => g.total,
                    render: (g) => `${((g.total / groups.reduce((s, x) => s + x.total, 0)) * 100).toFixed(1)}%` },
                  { key: "help", header: "What it is", wrap: true, render: (g) => <span className="text-muted">{GROUP_HELP[g.group] ?? ""}</span> },
                ]} />
              </Card>
            ))}
          </>
        )}
    </>
  );
}
