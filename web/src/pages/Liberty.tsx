import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BookMarked, Cpu, Layers, Zap } from "lucide-react";
import { postJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { Alert, Badge, Card, Chips, EmptyState, KpiGrid, LoadingBlock, PageHeader, Segmented, Select, Spinner, Tabs } from "../components/ui";
import { cx, PALETTE } from "../lib/format";

type CellSummary = {
  name: string; family: string; strength: number | null; area: number; leakage: number | null; footprint: string;
  kind: string; function: string; inputs: string[]; outputs: string[]; typical_delay: number | null;
  pin_count: number; arc_count: number; max_input_cap: number | null;
};
type Table = { template: string; variable_1: string; variable_2: string; index_1: number[]; index_2: number[]; values: number[][] };
type Arc = { from: string; to: string; timing_sense: string; timing_type: string; tables: Record<string, Table> };
type CellDetail = CellSummary & {
  pins: { name: string; direction: string; capacitance: number | null; function: string; clock: boolean; max_capacitance: number | null }[];
  arcs: Arc[];
};
type Lib = {
  error?: string; name: string; units: Record<string, string>;
  operating_conditions: { name: string; process: number | null; voltage: number | null; temperature: number | null };
  cells: CellSummary[];
};

const KIND_TONE: Record<string, "neutral" | "info" | "warn"> = { combinational: "neutral", "flip-flop": "info", latch: "warn" };

function heat(v: number, lo: number, hi: number) {
  const t = hi > lo ? (v - lo) / (hi - lo) : 0;
  return `color-mix(in srgb, #e5484d ${Math.round(t * 55)}%, color-mix(in srgb, #3b74e6 ${Math.round((1 - t) * 30)}%, transparent))`;
}

function NldmTable({ t, unit }: { t: Table; unit: string }) {
  const flat = t.values.flat();
  const lo = Math.min(...flat), hi = Math.max(...flat);
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1 text-[12.5px] tabular-nums">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-[11px] font-medium text-faint">{t.variable_1.replace(/_/g, " ")} ↓ / {t.variable_2.replace(/_/g, " ")} →</th>
            {t.index_2.map((v) => <th key={v} className="px-2 py-1 font-mono font-semibold text-muted">{v}</th>)}
          </tr>
        </thead>
        <tbody>
          {t.values.map((row, i) => (
            <tr key={i}>
              <th className="px-2 py-1 text-right font-mono font-semibold text-muted">{t.index_1[i]}</th>
              {row.map((v, j) => (
                <td key={j} className="rounded-md px-3 py-1.5 text-center font-mono" style={{ background: heat(v, lo, hi) }} title={`${v} ${unit}`}>{v.toFixed(4)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Liberty() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("cells");
  const [kinds, setKinds] = useState<string[]>(["combinational", "flip-flop", "latch"]);
  const [cellName, setCellName] = useState("");
  const [cell, setCell] = useState<CellDetail | null>(null);
  const [cellLoading, setCellLoading] = useState(false);
  const [arcIdx, setArcIdx] = useState(0);
  const [tableName, setTableName] = useState("cell_rise");
  const [view, setView] = useState<"chart" | "table">("chart");
  const [family, setFamily] = useState("");
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Lib>("/api/pd/liberty", file);
  const ok = data && !data.error;

  useEffect(() => { if (ok && !data.cells.some((c) => c.name === cellName)) setCellName(data.cells.find((c) => c.family.startsWith("NAND"))?.name ?? data.cells[0].name); }, [ok, data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!file || !cellName) return;
    setCellLoading(true);
    postJSON<CellDetail>("/api/pd/liberty/cell", { ...file, cell: cellName })
      .then((c) => { setCell(c); setArcIdx(0); setTableName(Object.keys(c.arcs[0]?.tables ?? {})[0] ?? "cell_rise"); })
      .catch(() => setCell(null)).finally(() => setCellLoading(false));
  }, [file, cellName]);

  const families = useMemo(() => {
    if (!ok) return [];
    const m = new Map<string, CellSummary[]>();
    data.cells.forEach((c) => { if (c.strength != null) m.set(c.family, [...(m.get(c.family) ?? []), c]); });
    return [...m.entries()].filter(([, cs]) => cs.length > 1).map(([f, cs]) => ({ family: f, cells: cs.sort((a, b) => (a.strength ?? 0) - (b.strength ?? 0)) }));
  }, [ok, data]);
  const fam = families.find((f) => f.family === family) ?? families[0];
  const arc = cell?.arcs[arcIdx];
  const table = arc?.tables[tableName];
  const timeUnit = ok ? data.units.time : "";
  const chartData = table ? table.index_2.map((load, j) => ({ load, ...Object.fromEntries(table.index_1.map((s, i) => [`slew ${s}`, table.values[i][j]])) })) : [];

  return (
    <>
      <PageHeader area="Physical design" title="Liberty Explorer" icon={BookMarked}
        description="Browse a standard-cell library (.lib): cell areas, leakage, pins and functions, and the NLDM delay tables as heatmaps and charts. Compare drive strengths side by side." />
      <Card className="mb-6">
        <FileSource label="Liberty library" examples={["lib/vt_demo.lib"]} accept=".lib,.liberty" onChange={setFiles} />
      </Card>

      {error && <Alert tone="bad" title="Request failed">{error}</Alert>}
      {!file ? <EmptyState icon={BookMarked} title="No library yet" text="Upload a .lib file from your PDK or standard-cell vendor." />
        : loading && !data ? <LoadingBlock label="Parsing library…" />
        : data?.error ? <Alert tone="bad">{data.error}</Alert>
        : ok && (
          <>
            <KpiGrid items={[
              { label: "Library", value: data.name },
              { label: "Cells", value: data.cells.length, note: `${data.cells.filter((c) => c.kind !== "combinational").length} sequential` },
              { label: "Corner", value: data.operating_conditions.name || "–", note: `${data.operating_conditions.voltage ?? "?"} V · ${data.operating_conditions.temperature ?? "?"} °C`, tone: "info" },
              { label: "Drive families", value: families.length, note: families.slice(0, 3).map((f) => f.family).join(", ") || undefined },
              { label: "Units", value: data.units.time || "–", note: `cap ${data.units.capacitive_load || "?"} · leak ${data.units.leakage_power || "?"}` },
            ]} />
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "cells", label: "Cells", icon: Layers, count: data.cells.length },
              { id: "detail", label: "Cell detail & timing", icon: Cpu },
              { id: "drive", label: "Drive strengths", icon: Zap, count: families.length },
            ]} />
            {tab === "cells" && (
              <Card bodyClass="p-4">
                <div className="mb-4"><Chips selected={kinds} onChange={setKinds} options={["combinational", "flip-flop", "latch"].map((k) => ({
                  value: k, label: k, count: data.cells.filter((c) => c.kind === k).length }))} /></div>
                <DataTable rows={data.cells.filter((c) => kinds.includes(c.kind))} searchable columns={[
                  { key: "name", header: "Cell", render: (c) => (
                    <button className="font-mono font-semibold text-brand hover:underline" onClick={() => { setCellName(c.name); setTab("detail"); }}>{c.name}</button>) },
                  { key: "kind", header: "Kind", render: (c) => <Badge tone={KIND_TONE[c.kind]}>{c.kind}</Badge> },
                  { key: "function", header: "Function", mono: true },
                  { key: "inputs", header: "Inputs", value: (c) => c.inputs.join(" "), mono: true },
                  { key: "area", header: "Area", align: "right", render: (c) => c.area.toFixed(3) },
                  { key: "leakage", header: `Leakage (${data.units.leakage_power})`, align: "right", render: (c) => c.leakage?.toFixed(3) ?? "–" },
                  { key: "max_input_cap", header: "Max in-cap", align: "right", render: (c) => c.max_input_cap?.toFixed(5) ?? "–" },
                  { key: "typical_delay", header: `Typ. delay (${timeUnit})`, align: "right", render: (c) => c.typical_delay?.toFixed(4) ?? "–" },
                ]} />
              </Card>
            )}
            {tab === "detail" && (
              <div className="space-y-5">
                <div className="flex flex-wrap items-end gap-3">
                  <div className="w-56"><Select value={cellName} onChange={setCellName} options={data.cells.map((c) => ({ value: c.name, label: c.name }))} /></div>
                  {cellLoading && <Spinner />}
                </div>
                {cell && (
                  <div className="grid gap-5 xl:grid-cols-[2fr_3fr]">
                    <div className="space-y-5">
                      <Card title={<span className="font-mono">{cell.name}</span>} subtitle={cell.function ? `Y = ${cell.function}` : cell.kind}>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[13.5px]">
                          {[["Kind", cell.kind], ["Area", cell.area.toFixed(3)], ["Leakage", `${cell.leakage ?? "–"} ${data.units.leakage_power}`],
                            ["Footprint", cell.footprint || "–"], ["Drive strength", cell.strength ? `X${cell.strength}` : "–"],
                            ["Timing arcs", String(cell.arcs.length)]].map(([k, v]) => (
                            <div key={k}><dt className="text-[12px] text-faint">{k}</dt><dd className="font-medium">{v}</dd></div>))}
                        </dl>
                      </Card>
                      <Card title="Pins" bodyClass="p-3">
                        <DataTable rows={cell.pins} dense columns={[
                          { key: "name", header: "Pin", mono: true, render: (p) => <span className="font-mono font-semibold">{p.name}{p.clock && <Badge tone="info" className="ml-2">clock</Badge>}</span> },
                          { key: "direction", header: "Dir" },
                          { key: "capacitance", header: "Cap", align: "right", render: (p) => p.capacitance?.toFixed(5) ?? "–" },
                          { key: "function", header: "Function", mono: true, render: (p) => p.function || "–" },
                        ]} />
                      </Card>
                    </div>
                    <Card title="Timing tables (NLDM)" subtitle={arc ? `${arc.from} → ${arc.to} · ${arc.timing_type}${arc.timing_sense ? " · " + arc.timing_sense : ""}` : "no timing arcs"}
                      actions={<Segmented size="sm" value={view} onChange={setView} options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />}>
                      {arc ? (
                        <>
                          <div className="mb-4 flex flex-wrap gap-3">
                            <div className="w-48"><Select value={String(arcIdx)} onChange={(v) => { setArcIdx(Number(v)); setTableName(Object.keys(cell.arcs[Number(v)].tables)[0]); }}
                              options={cell.arcs.map((a, i) => ({ value: String(i), label: `${a.from} → ${a.to} (${a.timing_type})` }))} /></div>
                            <div className="flex flex-wrap gap-1.5">
                              {Object.keys(arc.tables).map((n) => (
                                <button key={n} onClick={() => setTableName(n)}
                                  className={cx("rounded-md px-2.5 py-1 font-mono text-[12px]", n === tableName ? "bg-brand text-white" : "bg-surface-3 text-muted hover:text-fg")}>{n}</button>
                              ))}
                            </div>
                          </div>
                          {table && (view === "table" ? <NldmTable t={table} unit={timeUnit} /> : (
                            <div className="h-80">
                              <ResponsiveContainer>
                                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 18 }}>
                                  <CartesianGrid stroke="var(--line)" />
                                  <XAxis dataKey="load" type="number" domain={["dataMin", "dataMax"]} stroke="var(--faint)" fontSize={12}
                                    label={{ value: `output load (${data.units.capacitive_load || "cap"})`, position: "insideBottom", offset: -10, fill: "var(--muted)", fontSize: 12 }} />
                                  <YAxis stroke="var(--faint)" fontSize={12} width={60} unit={` ${timeUnit.replace(/^1/, "")}`} />
                                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12.5 }}
                                    formatter={(v) => Number(v).toFixed(4)} labelFormatter={(l) => `load ${l}`} />
                                  <Legend verticalAlign="top" height={28} />
                                  {table.index_1.map((s, i) => <Line key={s} dataKey={`slew ${s}`} stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          ))}
                          <p className="mt-3 text-[12.5px] text-muted">Each line is one input slew. Steeper lines = weaker drive (delay grows faster with load).</p>
                        </>
                      ) : <p className="text-muted">This cell has no timing arcs.</p>}
                    </Card>
                  </div>
                )}
              </div>
            )}
            {tab === "drive" && (fam ? (
              <div className="grid gap-5 xl:grid-cols-[2fr_3fr]">
                <Card title="Family" actions={<div className="w-40"><Select value={fam.family} onChange={setFamily} options={families.map((f) => ({ value: f.family, label: f.family }))} /></div>} bodyClass="p-3">
                  <DataTable rows={fam.cells} dense columns={[
                    { key: "name", header: "Cell", mono: true },
                    { key: "strength", header: "Drive", align: "right", render: (c) => `X${c.strength}` },
                    { key: "area", header: "Area", align: "right", render: (c) => c.area.toFixed(3) },
                    { key: "leakage", header: "Leakage", align: "right", render: (c) => c.leakage?.toFixed(2) ?? "–" },
                    { key: "typical_delay", header: "Typ. delay", align: "right", render: (c) => c.typical_delay?.toFixed(4) ?? "–" },
                  ]} />
                  <p className="mt-3 px-1 text-[12.5px] text-muted">Bigger cells are faster under load but cost area, leakage and input capacitance: the classic sizing trade-off.</p>
                </Card>
                <Card title={`${fam.family}: area and delay vs drive strength`}>
                  <div className="h-80">
                    <ResponsiveContainer>
                      <LineChart data={fam.cells.map((c) => ({ drive: `X${c.strength}`, area: c.area, delay: c.typical_delay }))} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
                        <CartesianGrid stroke="var(--line)" />
                        <XAxis dataKey="drive" stroke="var(--faint)" fontSize={12} />
                        <YAxis yAxisId="a" stroke={PALETTE[0]} fontSize={12} width={50} />
                        <YAxis yAxisId="d" orientation="right" stroke={PALETTE[1]} fontSize={12} width={60} />
                        <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12.5 }} formatter={(v) => Number(v).toFixed(4)} />
                        <Legend verticalAlign="top" height={28} />
                        <Line yAxisId="a" dataKey="area" name="area" stroke={PALETTE[0]} strokeWidth={2.2} dot={{ r: 4 }} isAnimationActive={false} />
                        <Line yAxisId="d" dataKey="delay" name={`typ. delay (${timeUnit})`} stroke={PALETTE[1]} strokeWidth={2.2} dot={{ r: 4 }} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              </div>
            ) : <EmptyState icon={Zap} title="No drive-strength families" text="Cells named like NAND2_X1 / NAND2_X2 are grouped automatically." />)}
          </>
        )}
    </>
  );
}
