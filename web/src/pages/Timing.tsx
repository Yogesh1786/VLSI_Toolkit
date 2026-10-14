import { useMemo, useState } from "react";
import { ChartColumn, Download, Flag, Route, Timer } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { SlackHistogram } from "../components/charts";
import {
  Alert,
  Button,
  Card,
  Chips,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  StatusBadge,
  Tabs,
  Toggle,
  type KpiItem,
} from "../components/ui";
import { downloadText, toCSV } from "../lib/format";

type Path = {
  startpoint: string;
  endpoint: string;
  path_group: string;
  path_type: string;
  arrival: number | null;
  required: number | null;
  slack: number | null;
  check: string;
  violated: boolean;
};
type Summary = Record<
  string,
  { paths: number; violations: number; wns: number | null; tns: number }
>;

const CHECK_COLOR: Record<string, string> = {
  setup: "#3b74e6",
  hold: "#e08a00",
};
const f3 = (v: number | null) => (v == null ? "–" : v.toFixed(3));

export default function Timing() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("dist");
  const [checks, setChecks] = useState<string[]>(["setup", "hold"]);
  const [onlyBad, setOnlyBad] = useState(false);
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<{
    paths: Path[];
    summary: Summary;
  }>("/api/pd/timing", file);

  const paths = (data?.paths ?? []).filter((p) => p.slack != null);
  const summary = data?.summary ?? {};
  const order = Object.keys(summary).sort(
    (a, b) => Number(a !== "setup") - Number(b !== "setup"),
  );
  const failing = paths.filter((p) => p.violated).length;
  const endpoints = useMemo(() => {
    const m = new Map<
      string,
      { endpoint: string; violations: number; worst: number }
    >();
    paths
      .filter((p) => p.violated)
      .forEach((p) => {
        const e = m.get(p.endpoint) ?? {
          endpoint: p.endpoint,
          violations: 0,
          worst: 0,
        };
        e.violations += 1;
        e.worst = Math.min(e.worst, p.slack!);
        m.set(p.endpoint, e);
      });
    return [...m.values()].sort(
      (a, b) => b.violations - a.violations || a.worst - b.worst,
    );
  }, [paths]);

  const kpis: KpiItem[] = order.flatMap((c) => {
    const s = summary[c];
    return [
      {
        label: `${c} WNS`,
        value: `${f3(s.wns)} ns`,
        note: s.violations
          ? `${s.violations} / ${s.paths} paths violate`
          : "MET",
        tone: s.violations ? "bad" : "good",
        hint: "Worst Negative Slack: the most negative slack. Below 0 = timing failure.",
      },
      {
        label: `${c} TNS`,
        value: `${f3(s.tns)} ns`,
        hint: "Total Negative Slack: sum of all negative slacks.",
      },
    ] as KpiItem[];
  });
  kpis.push({
    label: "Paths analyzed",
    value: paths.length,
    note: failing ? `${failing} violating` : "all met",
    tone: failing ? "bad" : "good",
  });

  return (
    <>
      <PageHeader
        area="Physical design"
        title="Timing (STA)"
        icon={Timer}
        description="Analyze a static timing report from OpenSTA, PrimeTime or Vivado: WNS/TNS per check, the slack distribution and the worst paths."
        actions={
          data ? (
            <Button
              icon={Download}
              onClick={() =>
                downloadText("timing_paths.csv", toCSV(paths), "text/csv")
              }
            >
              Export CSV
            </Button>
          ) : undefined
        }
      />
      <Card className="mb-6">
        <FileSource
          label="Timing report"
          examples={["sta_report.rpt"]}
          wsKinds={["timing"]}
          onChange={setFiles}
        />
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!file ? (
        <EmptyState
          icon={Timer}
          title="No report yet"
          text="Upload the output of report_checks (OpenSTA) or report_timing (PrimeTime / Vivado)."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : !paths.length ? (
        <Alert tone="bad" title="No timing paths found">
          Expected "Startpoint:" blocks (OpenSTA/PrimeTime) or "Slack (...)"
          blocks (Vivado).
        </Alert>
      ) : (
        <>
          <KpiGrid items={kpis} />
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { id: "dist", label: "Slack distribution", icon: ChartColumn },
              {
                id: "paths",
                label: "Worst paths",
                icon: Route,
                count: paths.length,
              },
              {
                id: "ep",
                label: "Endpoints",
                icon: Flag,
                count: endpoints.length,
              },
            ]}
          />
          {tab === "dist" && (
            <Card
              title="Slack distribution"
              subtitle="Bars left of the red line are failing paths"
            >
              <SlackHistogram
                series={order.map((c) => ({
                  name: c,
                  color: CHECK_COLOR[c] ?? "#7c4fd6",
                  values: paths
                    .filter((p) => p.check === c)
                    .map((p) => p.slack!),
                }))}
              />
              <p className="mt-4 text-[13px] text-muted">
                Tip: hold violations usually need delay buffers on short paths;
                setup violations need faster logic, re-pipelining or a slower
                clock.
              </p>
            </Card>
          )}
          {tab === "paths" && (
            <Card bodyClass="p-4">
              <div className="mb-4 flex flex-wrap items-center gap-5">
                <Chips
                  selected={checks}
                  onChange={setChecks}
                  options={order.map((c) => ({
                    value: c,
                    label: c,
                    count: summary[c].paths,
                  }))}
                />
                <Toggle
                  checked={onlyBad}
                  onChange={setOnlyBad}
                  label="Only violating paths"
                />
              </div>
              <DataTable
                rows={paths.filter(
                  (p) => checks.includes(p.check) && (!onlyBad || p.violated),
                )}
                initialSort={{ key: "slack", dir: "asc" }}
                searchable
                columns={[
                  {
                    key: "status",
                    header: "Status",
                    value: (p) => (p.violated ? 0 : 1),
                    render: (p) => (
                      <StatusBadge status={p.violated ? "VIOLATED" : "MET"} />
                    ),
                  },
                  {
                    key: "check",
                    header: "Check",
                    render: (p) => (
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="size-2 rounded-full"
                          style={{ background: CHECK_COLOR[p.check] }}
                        />
                        {p.check}
                      </span>
                    ),
                  },
                  {
                    key: "slack",
                    header: "Slack (ns)",
                    align: "right",
                    value: (p) => p.slack,
                    render: (p) => (
                      <span
                        className={p.violated ? "font-semibold text-bad" : ""}
                      >
                        {f3(p.slack)}
                      </span>
                    ),
                  },
                  { key: "startpoint", header: "Startpoint", mono: true },
                  { key: "endpoint", header: "Endpoint", mono: true },
                  { key: "path_group", header: "Group" },
                  {
                    key: "arrival",
                    header: "Arrival",
                    align: "right",
                    render: (p) => f3(p.arrival),
                  },
                  {
                    key: "required",
                    header: "Required",
                    align: "right",
                    render: (p) => f3(p.required),
                  },
                ]}
              />
            </Card>
          )}
          {tab === "ep" &&
            (endpoints.length === 0 ? (
              <Alert tone="good" title="No violating endpoints" />
            ) : (
              <Card
                title="Endpoints with most violations"
                subtitle="Fixing these first clears the most paths"
                bodyClass="p-4"
              >
                <DataTable
                  rows={endpoints}
                  columns={[
                    { key: "endpoint", header: "Endpoint", mono: true },
                    {
                      key: "violations",
                      header: "Violating paths",
                      render: (e) => (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-28 overflow-hidden rounded-full bg-surface-3">
                            <div
                              className="h-full rounded-full bg-bad"
                              style={{
                                width: `${(e.violations / endpoints[0].violations) * 100}%`,
                              }}
                            />
                          </div>
                          {e.violations}
                        </div>
                      ),
                    },
                    {
                      key: "worst",
                      header: "Worst slack (ns)",
                      align: "right",
                      render: (e) => (
                        <span className="font-semibold text-bad">
                          {e.worst.toFixed(3)}
                        </span>
                      ),
                    },
                  ]}
                />
              </Card>
            ))}
        </>
      )}
    </>
  );
}
