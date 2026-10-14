import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownRight,
  ArrowUpRight,
  ChartSpline,
  Database,
  Minus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { getJSON, postJSON, request } from "../lib/api";
import { useWorkspace } from "../lib/workspace";
import { DataTable } from "../components/DataTable";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Select,
} from "../components/ui";
import { cx, TONE_HEX } from "../lib/format";

type Point = { ts: number; value: number; id: number };
type Snapshot = {
  id: number;
  ts: number;
  workspace: string;
  label: string;
  metrics: Record<string, number>;
  demo: boolean;
};
type Info = {
  label: string;
  unit: string;
  better: "up" | "down" | null;
  group: string;
};
type History = {
  workspace: string;
  snapshots: Snapshot[];
  trends: Record<string, Point[]>;
  metrics: Record<string, Info>;
  workspaces: { workspace: string; snapshots: number; last: number }[];
};

const fmt = (v: number, unit: string) =>
  unit === "ratio"
    ? `${(v * 100).toFixed(1)}%`
    : unit === "ns"
      ? `${v.toFixed(3)} ns`
      : unit === "%"
        ? `${v}`
        : unit === "mW"
          ? `${+v.toFixed(4)} mW`
          : `${+v.toFixed(3)}`;
const day = (ts: number) =>
  new Date(ts * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
const when = (ts: number) =>
  new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

function TrendCard({
  k,
  info,
  points,
}: {
  k: string;
  info: Info;
  points: Point[];
}) {
  const last = points[points.length - 1].value;
  const prev = points.length > 1 ? points[points.length - 2].value : last;
  const delta = last - prev;
  const good =
    info.better == null || Math.abs(delta) < 1e-9
      ? null
      : (info.better === "up") === delta > 0;
  const color = good == null ? "#3b74e6" : good ? TONE_HEX.good : TONE_HEX.bad;
  const Icon =
    Math.abs(delta) < 1e-9 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold tracking-[0.1em] text-faint uppercase">
            {info.label}
          </div>
          <div className="mt-1 text-[22px] font-semibold tabular-nums">
            {fmt(last, info.unit)}
          </div>
        </div>
        <span
          className={cx(
            "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[12px] font-semibold",
            good == null
              ? "bg-surface-3 text-muted"
              : good
                ? "bg-good/10 text-good"
                : "bg-bad/10 text-bad",
          )}
        >
          <Icon className="size-3.5" />
          {Math.abs(delta) < 1e-9
            ? "same"
            : fmt(Math.abs(delta), info.unit === "%" ? "" : info.unit)}
        </span>
      </div>
      <div className="mt-2 h-20">
        <ResponsiveContainer>
          <AreaChart
            data={points}
            margin={{ top: 4, right: 2, left: 2, bottom: 0 }}
          >
            <defs>
              <linearGradient id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="ts" hide />
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip
              labelFormatter={(t) => when(Number(t))}
              formatter={(v) => [fmt(Number(v), info.unit), info.label]}
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Area
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              fill={`url(#g-${k})`}
              isAnimationActive={false}
              dot={points.length < 20}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-faint">
        <span>{day(points[0].ts)}</span>
        <span>{points.length} runs</span>
        <span>{day(points[points.length - 1].ts)}</span>
      </div>
    </div>
  );
}

export default function Trends() {
  const { ws } = useWorkspace();
  const [selected, setSelected] = useState<string | null>(null);
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const target = selected ?? ws?.root ?? null;

  const load = () => {
    if (!target) return;
    getJSON<History>(`/api/history?workspace=${encodeURIComponent(target)}`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  };
  useEffect(load, [target]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      load();
    } finally {
      setBusy(false);
    }
  };
  const groups = useMemo(() => {
    if (!data) return [];
    const keys = Object.keys(data.metrics).filter(
      (k) => data.trends[k]?.length,
    );
    return [...new Set(keys.map((k) => data.metrics[k].group))].map((g) => ({
      group: g,
      keys: keys.filter((k) => data.metrics[k].group === g),
    }));
  }, [data]);
  const snaps = data?.snapshots ?? [];
  const hasDemo = snaps.some((s) => s.demo);
  const wsOptions = useMemo(() => {
    const list = new Set([
      ...(ws ? [ws.root] : []),
      ...(data?.workspaces.map((w) => w.workspace) ?? []),
    ]);
    return [...list].map((w) => ({
      value: w,
      label: w.split(/[\\/]/).pop() + "  ·  " + w,
    }));
  }, [ws, data]);

  return (
    <>
      <PageHeader
        area="Workspace"
        title="Trends"
        icon={ChartSpline}
        description="Every saved workspace analysis becomes a point on these charts: follow lint, regression, timing and AXI health from day to day, and spot the night things went wrong."
        actions={
          wsOptions.length > 1 ? (
            <div className="w-80">
              <Select
                value={target ?? ""}
                onChange={setSelected}
                options={wsOptions}
              />
            </div>
          ) : undefined
        }
      />
      {error && (
        <Alert tone="bad" title="Could not load the history">
          {error}
        </Alert>
      )}
      {!data ? (
        <LoadingBlock label="Loading history…" />
      ) : snaps.length === 0 ? (
        <>
          <EmptyState
            icon={Database}
            title="No saved runs yet"
            text="Open the Workspace page and press Analyze with “Save to history” on. Each run adds a point here. Or load two weeks of demo data to see how it looks."
          />
          <div className="mt-4 flex justify-center gap-3">
            <Link to="/workspace">
              <Button variant="primary">Go to Workspace</Button>
            </Link>
            <Button
              icon={Sparkles}
              disabled={busy || !target}
              onClick={() =>
                act(() =>
                  postJSON("/api/history/demo", {
                    workspace: target,
                    days: 14,
                  }),
                )
              }
            >
              Load demo history
            </Button>
          </div>
        </>
      ) : (
        <>
          {snaps.length < 3 && !hasDemo && (
            <Alert tone="info" title="Trends need a few runs">
              Analyze the workspace on different days to build the trend, or{" "}
              <button
                className="font-medium text-brand hover:underline"
                disabled={busy}
                onClick={() =>
                  act(() =>
                    postJSON("/api/history/demo", {
                      workspace: target,
                      days: 14,
                    }),
                  )
                }
              >
                load two weeks of demo history
              </button>
              .
            </Alert>
          )}
          {hasDemo && (
            <Alert tone="info" title="Demo data is shown">
              Points labelled “(demo)” are generated examples.{" "}
              <button
                className="font-medium text-brand hover:underline"
                onClick={() =>
                  act(() =>
                    request(
                      `/api/history?workspace=${encodeURIComponent(target!)}&demo_only=true`,
                      { method: "DELETE" },
                    ),
                  )
                }
              >
                Remove demo data
              </button>
            </Alert>
          )}
          <KpiGrid
            items={[
              {
                label: "Saved runs",
                value: snaps.length,
                note: `since ${day(snaps[snaps.length - 1].ts)}`,
              },
              {
                label: "Last run",
                value: day(snaps[0].ts),
                note: snaps[0].label || when(snaps[0].ts),
              },
              {
                label: "Health score",
                value: snaps[0].metrics.health_score ?? "–",
                tone:
                  (snaps[0].metrics.health_score ?? 0) >= 80
                    ? "good"
                    : (snaps[0].metrics.health_score ?? 0) >= 50
                      ? "warn"
                      : "bad",
                note:
                  snaps.length > 1 && snaps[1].metrics.health_score != null
                    ? `was ${snaps[1].metrics.health_score}`
                    : undefined,
              },
              {
                label: "Metrics tracked",
                value: Object.keys(data.trends).filter((k) => data.metrics[k])
                  .length,
              },
              {
                label: "Workspace",
                value: (target ?? "").split(/[\\/]/).pop() ?? "",
                note: ws?.root === target ? "active" : "other",
              },
            ]}
          />
          {groups.map((g) => (
            <section key={g.group} className="mb-6">
              <h2 className="mb-3 text-[15px] font-semibold">{g.group}</h2>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {g.keys.map((k) => (
                  <TrendCard
                    key={k}
                    k={k}
                    info={data.metrics[k]}
                    points={data.trends[k]}
                  />
                ))}
              </div>
            </section>
          ))}
          <Card title="Saved runs" subtitle="Newest first" bodyClass="p-4">
            <DataTable
              rows={snaps}
              maxHeight={420}
              columns={[
                {
                  key: "ts",
                  header: "When",
                  render: (s) => when(s.ts),
                  value: (s) => s.ts,
                },
                {
                  key: "label",
                  header: "Label",
                  render: (s) => (
                    <span>
                      {s.label || "–"}
                      {s.demo && <Badge className="ml-2">demo</Badge>}
                    </span>
                  ),
                },
                {
                  key: "health",
                  header: "Health",
                  align: "right",
                  value: (s) => s.metrics.health_score,
                  render: (s) => s.metrics.health_score ?? "–",
                },
                {
                  key: "lint",
                  header: "Lint err",
                  align: "right",
                  value: (s) => s.metrics.lint_errors,
                  render: (s) => s.metrics.lint_errors ?? "–",
                },
                {
                  key: "pass",
                  header: "Pass rate",
                  align: "right",
                  value: (s) => s.metrics.reg_pass_rate,
                  render: (s) =>
                    s.metrics.reg_pass_rate != null
                      ? `${(s.metrics.reg_pass_rate * 100).toFixed(1)}%`
                      : "–",
                },
                {
                  key: "wns",
                  header: "Setup WNS",
                  align: "right",
                  value: (s) => s.metrics.setup_wns,
                  render: (s) =>
                    s.metrics.setup_wns != null ? (
                      <span
                        className={s.metrics.setup_wns < 0 ? "text-bad" : ""}
                      >
                        {s.metrics.setup_wns.toFixed(3)}
                      </span>
                    ) : (
                      "–"
                    ),
                },
                {
                  key: "axi",
                  header: "AXI err",
                  align: "right",
                  value: (s) => s.metrics.axi_errors,
                  render: (s) => s.metrics.axi_errors ?? "–",
                },
                {
                  key: "del",
                  header: "",
                  render: (s) => (
                    <button
                      title="Delete this run"
                      className="text-faint hover:text-bad"
                      onClick={() =>
                        act(() =>
                          request(`/api/history/${s.id}`, { method: "DELETE" }),
                        )
                      }
                    >
                      <Trash2 className="size-4" />
                    </button>
                  ),
                },
              ]}
            />
          </Card>
        </>
      )}
    </>
  );
}
