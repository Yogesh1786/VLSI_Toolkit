import { useState } from "react";
import { Boxes, Grid3x3, MapPinOff } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { DensityHeatmap } from "../components/charts";
import { Alert, BarList, Card, EmptyState, KpiGrid, LoadingBlock, PageHeader, Segmented, Tabs } from "../components/ui";
import { fmtInt, pct } from "../lib/format";

type Result = {
  design: string; die_w_um: number; die_h_um: number; die_um2: number; core_um2: number; rows: number; nets: number;
  instances: number; utilization: number | null; std_area: number; macro_area: number; has_lef: boolean;
  status: Record<string, number>; categories: { category: string; count: number; area: number }[];
  cells: { cell: string; category: string; count: number; area: number }[]; unplaced: string[]; missing_in_lef: string[];
  grid: number[][] | null; macro_bins: [number, number][];
};

export default function Floorplan() {
  const [defFiles, setDefFiles] = useState<SourceFile[] | null>(null);
  const [lefFiles, setLefFiles] = useState<SourceFile[] | null>(null);
  const [useLef, setUseLef] = useState<"yes" | "no">("yes");
  const [metric, setMetric] = useState<"count" | "area">("count");
  const [tab, setTab] = useState("map");
  const def = defFiles?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>("/api/pd/floorplan",
    def ? { def_file: def, lefs: useLef === "yes" ? lefFiles ?? [] : [] } : null);
  const util = data?.utilization ?? null;

  return (
    <>
      <PageHeader area="Physical design" title="Floorplan" icon={Grid3x3}
        description="Analyze a placed design (DEF): die and core area, utilization, cell mix and where cells are crowded. LEF files add cell sizes for area and utilization." />
      <Card className="mb-6">
        <div className="grid gap-6 lg:grid-cols-2">
          <FileSource label="DEF file" examples={["pd/demo.def"]} accept=".def" onChange={setDefFiles} />
          <div>
            <div className="mb-3 flex items-center gap-3">
              <span className="text-[13px] font-medium text-muted">Cell sizes (LEF)</span>
              <Segmented size="sm" value={useLef} onChange={setUseLef} options={[{ value: "yes", label: "Use LEF" }, { value: "no", label: "No LEF" }]} />
            </div>
            {useLef === "yes" ? <FileSource label="LEF files" multiple examples={["pd/demo.lef"]} accept=".lef" onChange={setLefFiles} />
              : <p className="text-[13.5px] text-muted">Without LEF you get cell counts only, no areas or utilization.</p>}
          </div>
        </div>
      </Card>

      {error && <Alert tone="bad" title="Request failed">{error}</Alert>}
      {!def ? <EmptyState icon={Grid3x3} title="No DEF yet" text="Export DEF from your P&R tool (write_def in OpenROAD, defOut in Innovus) and upload it." />
        : loading && !data ? <LoadingBlock /> : data && (
          <>
            <KpiGrid items={[
              { label: "Design", value: data.design || "?" },
              { label: "Die area", value: fmtInt(Math.round(data.die_um2)), note: `µm² · ${+data.die_w_um.toFixed(2)} × ${+data.die_h_um.toFixed(2)} µm` },
              { label: "Core area", value: fmtInt(Math.round(data.core_um2)), note: `µm² · ${data.rows} rows` },
              { label: "Utilization", value: util == null ? "needs LEF" : pct(util), tone: util == null ? "neutral" : util > 0.8 ? "bad" : "good",
                note: util == null ? undefined : util > 0.8 ? "high: congestion risk" : "healthy",
                hint: "Std-cell area / (core area − macro area). Above ~80% routing gets hard." },
              { label: "Instances", value: fmtInt(data.instances), note: data.unplaced.length ? `${data.unplaced.length} unplaced` : `${fmtInt(data.nets)} nets`,
                tone: data.unplaced.length ? "bad" : "neutral" },
            ]} />
            {data.unplaced.length > 0 && <Alert tone="warn" title={`${data.unplaced.length} unplaced instance(s)`}>
              <MapPinOff className="mr-1 inline size-3.5" />{data.unplaced.slice(0, 12).join(", ")}</Alert>}
            {data.missing_in_lef.length > 0 && <Alert tone="warn" title="Cells missing from LEF">{data.missing_in_lef.slice(0, 12).join(", ")}</Alert>}
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "map", label: "Placement & cell mix", icon: Grid3x3 },
              { id: "cells", label: "Cell types", icon: Boxes, count: data.cells.length },
            ]} />
            {tab === "map" && (
              <div className="grid gap-5 xl:grid-cols-[3fr_2fr]">
                <Card title="Placement density" subtitle={data.has_lef ? "cell area per bin" : "cell count per bin"}>
                  {data.grid ? <DensityHeatmap grid={data.grid} macroBins={data.macro_bins} label={data.has_lef ? "Cell area (µm²)" : "Cells"} />
                    : <p className="text-muted">No DIEAREA in the DEF, so a map cannot be drawn.</p>}
                  <p className="mt-3 text-[13px] text-muted">Hot spots often turn into routing congestion later.</p>
                </Card>
                <Card title="Cell mix" actions={data.has_lef ? <Segmented size="sm" value={metric} onChange={setMetric}
                  options={[{ value: "count", label: "Instances" }, { value: "area", label: "Area" }]} /> : undefined}>
                  <BarList items={[...data.categories].sort((a, b) => b[metric] - a[metric]).map((c) => ({ label: c.category, value: c[metric] }))}
                    format={(v) => (metric === "area" ? `${fmtInt(Math.round(v))} µm²` : fmtInt(v))} />
                  {data.has_lef && <div className="mt-5 grid grid-cols-2 gap-3 border-t border-line pt-4 text-[13px]">
                    <div><div className="text-faint">Std-cell area</div><div className="font-semibold tabular-nums">{fmtInt(Math.round(data.std_area))} µm²</div></div>
                    <div><div className="text-faint">Macro area</div><div className="font-semibold tabular-nums">{fmtInt(Math.round(data.macro_area))} µm²</div></div>
                  </div>}
                </Card>
              </div>
            )}
            {tab === "cells" && (
              <Card bodyClass="p-4">
                <DataTable rows={data.cells} searchable initialSort={{ key: "count", dir: "desc" }} columns={[
                  { key: "cell", header: "Cell", mono: true },
                  { key: "category", header: "Category" },
                  { key: "count", header: "Count", align: "right" },
                  { key: "area", header: "Area (µm²)", align: "right", render: (c) => (data.has_lef ? c.area.toFixed(2) : "–") },
                ]} />
              </Card>
            )}
          </>
        )}
    </>
  );
}
