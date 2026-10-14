import { useEffect, useMemo, useState } from "react";
import { Activity, CircleHelp, Table, TriangleAlert, Zap } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { WaveformViewer } from "../components/charts";
import {
  Alert,
  Card,
  Chips,
  EmptyState,
  Field,
  KpiGrid,
  LoadingBlock,
  NumberInput,
  PageHeader,
  Tabs,
} from "../components/ui";

type Stat = {
  name: string;
  width: number;
  toggles: number;
  final: string;
  clock: string | null;
  glitches: number;
  x_after: number | null;
};
type Result = {
  error?: string;
  timescale: string;
  timescale_s: number;
  end_time: number;
  stats: Stat[];
  signals: Record<string, { width: number; changes: [number, string][] }>;
};

export default function Waveform() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [glitch, setGlitch] = useState(2);
  const [xAfter, setXAfter] = useState<number | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [tab, setTab] = useState("wave");
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>(
    "/api/verif/vcd",
    file ? { ...file, glitch: Math.max(1, glitch), x_after: xAfter } : null,
  );
  const ok = data && !data.error;
  const names = useMemo(
    () => (ok ? Object.keys(data.signals) : []),
    [ok, data],
  );
  useEffect(() => {
    setPicked(names.slice(0, 10));
  }, [names.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  const stats = ok ? data.stats : [];
  const issues = stats.filter((s) => s.glitches || s.x_after != null);
  const idle = stats.filter((s) => s.toggles === 0);
  const clocks = stats.filter((s) => s.clock);
  const maxToggles = Math.max(1, ...stats.map((s) => s.toggles));

  return (
    <>
      <PageHeader
        area="Verification"
        title="Waveform Viewer"
        icon={Activity}
        description="Open a VCD dump in the browser: a zoomable waveform view plus automatic checks for clocks, glitches, X/Z values and idle signals."
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <FileSource
            label="VCD file"
            examples={["sample.vcd"]}
            accept=".vcd"
            onChange={setFiles}
          />
          <div className="grid grid-cols-2 gap-3 lg:w-[380px]">
            <Field
              label="Glitch threshold"
              hint="Pulses shorter than this many time units count as glitches"
            >
              <NumberInput value={glitch} onChange={setGlitch} min={1} />
            </Field>
            <Field
              label="Report X/Z after"
              hint="X before this time (during reset) is normal. Default: 10% of the simulation"
            >
              <NumberInput
                value={xAfter ?? (ok ? Math.floor(data.end_time / 10) : 0)}
                onChange={setXAfter}
                min={0}
              />
            </Field>
          </div>
        </div>
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!file ? (
        <EmptyState
          icon={Activity}
          title="No waveform yet"
          text="Upload a .vcd file written by your simulator ($dumpfile / $dumpvars)."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : data?.error ? (
        <Alert tone="bad">{data.error}</Alert>
      ) : (
        ok && (
          <>
            <KpiGrid
              items={[
                { label: "Signals", value: stats.length },
                {
                  label: "Simulation end",
                  value: `${+(data.end_time * data.timescale_s * 1e9).toPrecision(6)} ns`,
                  note: `timescale ${data.timescale}`,
                },
                {
                  label: "Clocks found",
                  value: clocks.length,
                  note:
                    clocks
                      .slice(0, 2)
                      .map((c) => c.clock!.split(",")[0])
                      .join(", ") || undefined,
                  tone: "info",
                },
                {
                  label: "Signals with issues",
                  value: issues.length,
                  note: issues.length ? "glitches / X values" : "none",
                  tone: issues.length ? "bad" : "good",
                },
                {
                  label: "Never toggled",
                  value: idle.length,
                  note: idle.length ? "check stimulus" : "none",
                  tone: idle.length ? "warn" : "good",
                },
              ]}
            />
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { id: "wave", label: "Waveforms", icon: Activity },
                {
                  id: "issues",
                  label: "Issues",
                  icon: TriangleAlert,
                  count: issues.length + idle.length,
                },
                {
                  id: "stats",
                  label: "Signal statistics",
                  icon: Table,
                  count: stats.length,
                },
              ]}
            />
            {tab === "wave" && (
              <Card bodyClass="p-4">
                <div className="mb-4">
                  <Chips
                    selected={picked}
                    onChange={setPicked}
                    options={names.map((n) => ({ value: n, label: n }))}
                  />
                </div>
                {picked.length ? (
                  <WaveformViewer
                    endTime={data.end_time}
                    timescale={data.timescale}
                    waves={names
                      .filter((n) => picked.includes(n))
                      .map((n) => ({ name: n, ...data.signals[n] }))}
                  />
                ) : (
                  <p className="py-8 text-center text-muted">
                    Select signals above to display them.
                  </p>
                )}
              </Card>
            )}
            {tab === "issues" && (
              <div>
                {!issues.length && !idle.length && (
                  <Alert
                    tone="good"
                    title="No glitches, X values or idle signals"
                  />
                )}
                {issues.map((s) => (
                  <div key={s.name}>
                    {s.glitches > 0 && (
                      <Alert tone="warn" title={s.name}>
                        <Zap className="mr-1 inline size-3.5" />
                        {s.glitches} glitch(es) narrower than {glitch} time
                        units
                      </Alert>
                    )}
                    {s.x_after != null && (
                      <Alert tone="bad" title={s.name}>
                        <CircleHelp className="mr-1 inline size-3.5" />
                        X/Z value still present at time {s.x_after} — missing
                        reset or undriven net?
                      </Alert>
                    )}
                  </div>
                ))}
                {idle.length > 0 && (
                  <Alert tone="info" title="Never toggled">
                    {idle.map((s) => s.name).join(", ")} — check that the
                    stimulus reaches them.
                  </Alert>
                )}
              </div>
            )}
            {tab === "stats" && (
              <Card bodyClass="p-4">
                <DataTable
                  rows={stats}
                  searchable
                  columns={[
                    { key: "name", header: "Signal", mono: true },
                    { key: "width", header: "Width", align: "right" },
                    {
                      key: "toggles",
                      header: "Toggles",
                      render: (s) => (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-3">
                            <div
                              className="h-full rounded-full bg-brand"
                              style={{
                                width: `${(s.toggles / maxToggles) * 100}%`,
                              }}
                            />
                          </div>
                          <span className="tabular-nums">{s.toggles}</span>
                        </div>
                      ),
                    },
                    { key: "final", header: "Final value", mono: true },
                    {
                      key: "clock",
                      header: "Clock",
                      render: (s) => s.clock ?? "–",
                    },
                    {
                      key: "glitches",
                      header: "Glitches",
                      align: "right",
                      render: (s) =>
                        s.glitches ? (
                          <span className="font-semibold text-warn">
                            {s.glitches}
                          </span>
                        ) : (
                          "–"
                        ),
                    },
                    {
                      key: "x_after",
                      header: "X/Z at",
                      align: "right",
                      render: (s) =>
                        s.x_after != null ? (
                          <span className="font-semibold text-bad">
                            {s.x_after}
                          </span>
                        ) : (
                          "–"
                        ),
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
