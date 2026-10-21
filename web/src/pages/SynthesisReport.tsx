import { useState } from "react";
import { Boxes, Cpu, Download, Layers } from "lucide-react";
import { useAnalysis, type SourceFile, initialExample } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import {
  Alert,
  BarList,
  Button,
  Card,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Segmented,
  StackedBar,
  Tabs,
  type KpiItem,
} from "../components/ui";
import { downloadText, fmtInt, PALETTE, toCSV } from "../lib/format";

type Module = {
  name: string;
  design: string;
  total_area: number;
  percent: number;
  instances: number;
  cells?: number | null;
  seq_cells?: number;
  comb_area?: number;
  seq_area?: number;
  macro_area?: number;
};
type Report = {
  format: "yosys" | "design_compiler";
  top: string | null;
  total_area: number;
  total_cells: number | null;
  comb_area: number | null;
  seq_area: number | null;
  buf_inv_area: number | null;
  macro_area: number | null;
  seq_cells: number | null;
  modules: Module[];
  cell_types: { cell: string; count: number; sequential: boolean }[];
};

const area = (v: number | null | undefined) =>
  v == null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: 2 });

export default function SynthesisReport() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("modules");
  const [example, setExample] = useState<string>(() =>
    initialExample("signoff/synth_yosys.rpt", { "signoff/synth_yosys.rpt": "signoff/synth_yosys.rpt", "signoff/synth_dc_area.rpt": "signoff/synth_dc_area.rpt" }),
  );
  const file = files?.[0] ?? null;
  const {
    data: r,
    loading,
    error,
  } = useAnalysis<Report>("/api/pd/synthesis", file);

  const split =
    r &&
    [
      { label: "Combinational", value: r.comb_area ?? 0, color: PALETTE[0] },
      { label: "Sequential", value: r.seq_area ?? 0, color: PALETTE[1] },
      {
        label: "Macro / black box",
        value: r.macro_area ?? 0,
        color: PALETTE[4],
      },
    ]
      .filter((p) => p.value > 0)
      .map((p) => ({ ...p, value: Math.round(p.value) }));

  const kpis: KpiItem[] = r
    ? [
        {
          label: "Total cell area",
          value: area(r.total_area),
          note: r.format === "yosys" ? "library units (µm²)" : "library units",
          hint: "Sum of the area of every standard cell and macro, from the Liberty library.",
        },
        {
          label: "Cells",
          value: r.total_cells == null ? "–" : fmtInt(r.total_cells),
          note: `top: ${r.top ?? "?"}`,
        },
        {
          label: "Sequential cells",
          value: r.seq_cells == null ? "–" : fmtInt(r.seq_cells),
          note:
            r.seq_cells != null && r.total_cells
              ? `${((r.seq_cells / r.total_cells) * 100).toFixed(1)}% of all cells`
              : undefined,
          hint: "Flip-flops and latches. A big jump between runs often means an unintended register or a lost memory inference.",
        },
        r.comb_area != null
          ? {
              label: "Combinational area",
              value: area(r.comb_area),
              note: `${((r.comb_area / r.total_area) * 100).toFixed(1)}%`,
              tone: "info",
            }
          : {
              label: "Modules",
              value: r.modules.length,
              note: "in the hierarchy",
            },
      ]
    : [];

  return (
    <>
      <PageHeader
        area="Physical design"
        title="Synthesis Report"
        icon={Cpu}
        description="Read a synthesis area report (Yosys stat or Design Compiler report_area -hierarchy): total area, the area of each module and the most-used cells."
        actions={
          r ? (
            <Button
              icon={Download}
              onClick={() =>
                downloadText("synth_modules.csv", toCSV(r.modules), "text/csv")
              }
            >
              Export CSV
            </Button>
          ) : undefined
        }
      />
      <Card className="mb-6">
        <div className="mb-4 flex flex-wrap items-center gap-3 text-[13px] text-muted">
          Example format
          <Segmented
            size="sm"
            value={example}
            onChange={setExample}
            options={[
              { value: "signoff/synth_yosys.rpt", label: "Yosys stat" },
              { value: "signoff/synth_dc_area.rpt", label: "Design Compiler" },
            ]}
          />
        </div>
        <FileSource
          label="Synthesis report"
          examples={[example]}
          wsKinds={["synth"]}
          onChange={setFiles}
        />
      </Card>

      {error && (
        <Alert tone="bad" title="Could not read the report">
          {error}
        </Alert>
      )}
      {!file ? (
        <EmptyState
          icon={Cpu}
          title="No report yet"
          text="Upload the output of Yosys 'stat -liberty cells.lib' or DC 'report_area -hierarchy'."
        />
      ) : loading && !r ? (
        <LoadingBlock />
      ) : (
        r && (
          <>
            <KpiGrid items={kpis} />
            {split && split.length > 0 && (
              <Card
                title="Area split"
                subtitle="Where the silicon goes"
                className="mb-6"
              >
                <StackedBar parts={split} />
              </Card>
            )}
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                {
                  id: "modules",
                  label: "Area by module",
                  icon: Layers,
                  count: r.modules.length,
                },
                ...(r.cell_types.length
                  ? [
                      {
                        id: "cells",
                        label: "Cell types",
                        icon: Boxes,
                        count: r.cell_types.length,
                      },
                    ]
                  : []),
              ]}
            />
            {tab === "modules" &&
              (r.modules.length === 0 ? (
                <Alert tone="info" title="No per-module data">
                  The report has totals only. Use report_area -hierarchy (DC) or
                  stat on the whole design (Yosys).
                </Alert>
              ) : (
                <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
                  <Card
                    title="Largest modules"
                    subtitle="Total area including instances"
                  >
                    <BarList
                      items={[...r.modules]
                        .filter((m) => m.name !== r.top || r.format === "yosys")
                        .sort((a, b) => b.total_area - a.total_area)
                        .slice(0, 8)
                        .map((m) => ({
                          label:
                            m.instances > 1
                              ? `${m.name} ×${m.instances}`
                              : m.name,
                          value: m.total_area,
                        }))}
                      format={(v) => area(v)}
                    />
                  </Card>
                  <Card bodyClass="p-4">
                    <DataTable
                      rows={r.modules}
                      initialSort={{ key: "total_area", dir: "desc" }}
                      searchable
                      columns={[
                        {
                          key: "name",
                          header: r.format === "yosys" ? "Module" : "Instance",
                          mono: true,
                        },
                        { key: "design", header: "Design", mono: true },
                        { key: "instances", header: "Inst.", align: "right" },
                        {
                          key: "total_area",
                          header: "Area",
                          align: "right",
                          render: (m) => area(m.total_area),
                        },
                        {
                          key: "percent",
                          header: "%",
                          align: "right",
                          render: (m) => (
                            <div className="flex items-center justify-end gap-2">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-3">
                                <div
                                  className="h-full rounded-full bg-brand"
                                  style={{
                                    width: `${Math.min(100, m.percent)}%`,
                                  }}
                                />
                              </div>
                              {m.percent.toFixed(1)}
                            </div>
                          ),
                        },
                        ...(r.format === "yosys"
                          ? [
                              {
                                key: "cells",
                                header: "Cells",
                                align: "right" as const,
                              },
                              {
                                key: "seq_cells",
                                header: "Flops",
                                align: "right" as const,
                              },
                            ]
                          : [
                              {
                                key: "comb_area",
                                header: "Comb.",
                                align: "right" as const,
                                render: (m: Module) => area(m.comb_area),
                              },
                              {
                                key: "seq_area",
                                header: "Seq.",
                                align: "right" as const,
                                render: (m: Module) => area(m.seq_area),
                              },
                            ]),
                      ]}
                    />
                  </Card>
                </div>
              ))}
            {tab === "cells" && (
              <Card bodyClass="p-4">
                <DataTable
                  rows={r.cell_types}
                  initialSort={{ key: "count", dir: "desc" }}
                  searchable
                  columns={[
                    { key: "cell", header: "Cell", mono: true },
                    {
                      key: "sequential",
                      header: "Kind",
                      render: (c) =>
                        c.sequential ? "sequential" : "combinational",
                    },
                    {
                      key: "count",
                      header: "Count",
                      align: "right",
                      render: (c) => fmtInt(c.count),
                    },
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
