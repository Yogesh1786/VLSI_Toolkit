import { useEffect, useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  ClipboardCheck,
  GitCompareArrows,
  Minus,
  Timer,
} from "lucide-react";
import { getJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import {
  Alert,
  Badge,
  Card,
  Chips,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Segmented,
  StatusBadge,
} from "../components/ui";
import { cx, downloadText, pct, toCSV, type Tone } from "../lib/format";

type RegRow = {
  test: string;
  change: string;
  old_status: string | null;
  new_status: string | null;
  old_signature: string;
  new_signature: string;
  signature_changed: boolean;
};
type RegResult = {
  old: { logs: number; tests: number; pass_rate: number };
  new: { logs: number; tests: number; pass_rate: number };
  counts: Record<string, number>;
  rows: RegRow[];
  new_signatures: string[];
  gone_signatures: string[];
  verdict: string;
};
type TimRow = {
  check: string;
  endpoint: string;
  old_slack: number | null;
  new_slack: number | null;
  delta: number | null;
  change: string;
};
type TimResult = {
  error?: string;
  verdict: string;
  counts: Record<string, number>;
  rows: TimRow[];
  checks: {
    check: string;
    old_wns: number | null;
    new_wns: number | null;
    old_tns: number;
    new_tns: number;
    old_violations: number;
    new_violations: number;
    delta_wns: number | null;
    delta_tns: number;
  }[];
};

const CHANGE: Record<string, { label: string; tone: Tone }> = {
  new_failure: { label: "New failure", tone: "bad" },
  fixed: { label: "Fixed", tone: "good" },
  still_failing: { label: "Still failing", tone: "warn" },
  still_passing: { label: "Still passing", tone: "neutral" },
  added: { label: "Added", tone: "info" },
  removed: { label: "Removed", tone: "neutral" },
  new_violation: { label: "New violation", tone: "bad" },
  degraded: { label: "Degraded", tone: "warn" },
  improved: { label: "Improved", tone: "good" },
  unchanged: { label: "Unchanged", tone: "neutral" },
};
const VERDICT: Record<string, { tone: Tone; title: string; text: string }> = {
  regressed: {
    tone: "bad",
    title: "Regressed",
    text: "Things got worse. Start with the red rows.",
  },
  improved: {
    tone: "good",
    title: "Improved",
    text: "Things got better and nothing new broke.",
  },
  mixed: {
    tone: "warn",
    title: "Mixed",
    text: "Some things improved, others got worse.",
  },
  unchanged: {
    tone: "info",
    title: "No change",
    text: "Both runs give the same results.",
  },
};
const f3 = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(3));

function Delta({
  v,
  betterWhenUp = true,
}: {
  v: number | null;
  betterWhenUp?: boolean;
}) {
  if (v == null) return <span className="text-faint">–</span>;
  if (Math.abs(v) < 0.0005)
    return (
      <span className="inline-flex items-center gap-1 text-muted">
        <Minus className="size-3.5" />0
      </span>
    );
  const good = betterWhenUp ? v > 0 : v < 0;
  const Icon = v > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-0.5 font-semibold tabular-nums",
        good ? "text-good" : "text-bad",
      )}
    >
      <Icon className="size-3.5" />
      {v > 0 ? "+" : ""}
      {v.toFixed(3)}
    </span>
  );
}

function SidePicker({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-3 text-[11px] font-semibold tracking-[0.12em] text-faint uppercase">
        {title}
      </div>
      {children}
    </div>
  );
}

function RegressionCompare() {
  const [prev, setPrev] = useState<string[]>([]),
    [cur, setCur] = useState<string[]>([]);
  const [oldF, setOldF] = useState<SourceFile[] | null>(null),
    [newF, setNewF] = useState<SourceFile[] | null>(null);
  const [show, setShow] = useState([
    "new_failure",
    "fixed",
    "still_failing",
    "added",
    "removed",
  ]);
  useEffect(() => {
    getJSON<string[]>("/api/examples?folder=regression_logs_prev")
      .then(setPrev)
      .catch(() => {});
    getJSON<string[]>("/api/examples?folder=regression_logs")
      .then(setCur)
      .catch(() => {});
  }, []);
  const { data, loading, error } = useAnalysis<RegResult>(
    "/api/compare/regress",
    oldF && newF ? { old: oldF, new: newF } : null,
  );
  const v = data ? VERDICT[data.verdict] : null;
  return (
    <>
      <Card className="mb-6">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr]">
          <SidePicker title="Before (e.g. last night)">
            {prev.length > 0 && (
              <FileSource
                label="Logs"
                multiple
                examples={prev}
                accept=".log,.txt,.out"
                onChange={setOldF}
              />
            )}
          </SidePicker>
          <ArrowRight className="hidden size-5 self-center text-faint lg:block" />
          <SidePicker title="After (e.g. tonight)">
            {cur.length > 0 && (
              <FileSource
                label="Logs"
                multiple
                examples={cur}
                accept=".log,.txt,.out"
                onChange={setNewF}
              />
            )}
          </SidePicker>
        </div>
      </Card>
      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!oldF || !newF ? (
        <EmptyState
          icon={GitCompareArrows}
          title="Pick both runs"
          text="Load the logs of two regression runs to see what changed."
        />
      ) : loading && !data ? (
        <LoadingBlock label="Comparing…" />
      ) : (
        data &&
        v && (
          <>
            <Alert tone={v.tone} title={`Verdict: ${v.title}`}>
              {v.text}
            </Alert>
            <KpiGrid
              items={[
                {
                  label: "Pass rate",
                  value: `${pct(data.old.pass_rate, 0)} → ${pct(data.new.pass_rate, 0)}`,
                  note:
                    data.new.pass_rate >= data.old.pass_rate
                      ? "up or same"
                      : "down",
                  tone:
                    data.new.pass_rate >= data.old.pass_rate ? "good" : "bad",
                },
                {
                  label: "New failures",
                  value: data.counts.new_failure,
                  tone: data.counts.new_failure ? "bad" : "good",
                  note: data.counts.new_failure ? "investigate first" : "none",
                },
                {
                  label: "Fixed",
                  value: data.counts.fixed,
                  tone: data.counts.fixed ? "good" : "neutral",
                  note: data.gone_signatures.length
                    ? `${data.gone_signatures.length} bug signature${data.gone_signatures.length > 1 ? "s" : ""} gone`
                    : undefined,
                },
                {
                  label: "Still failing",
                  value: data.counts.still_failing,
                  tone: data.counts.still_failing ? "warn" : "good",
                },
                {
                  label: "New bug signatures",
                  value: data.new_signatures.length,
                  tone: data.new_signatures.length ? "bad" : "good",
                  note: data.new_signatures.length ? "not seen before" : "none",
                },
              ]}
            />
            {data.new_signatures.length > 0 && (
              <Card
                title="New failure signatures"
                subtitle="Errors that did not exist in the previous run"
                className="mb-5"
                bodyClass="space-y-2 p-4"
              >
                {data.new_signatures.map((s) => (
                  <div
                    key={s}
                    className="rounded-lg border border-bad/25 bg-bad/5 px-3 py-2 font-mono text-[12.5px]"
                  >
                    {s}
                  </div>
                ))}
              </Card>
            )}
            <Card bodyClass="p-4">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <Chips
                  selected={show}
                  onChange={setShow}
                  options={[
                    "new_failure",
                    "fixed",
                    "still_failing",
                    "still_passing",
                    "added",
                    "removed",
                  ].map((c) => ({
                    value: c,
                    label: CHANGE[c].label,
                    tone: CHANGE[c].tone,
                    count: data.counts[c],
                  }))}
                />
                <button
                  className="text-[13px] font-medium text-brand hover:underline"
                  onClick={() =>
                    downloadText(
                      "regression_compare.csv",
                      toCSV(data.rows),
                      "text/csv",
                    )
                  }
                >
                  Export CSV
                </button>
              </div>
              <DataTable
                rows={data.rows.filter((r) => show.includes(r.change))}
                searchable
                initialSort={{ key: "change", dir: "asc" }}
                columns={[
                  {
                    key: "change",
                    header: "Change",
                    value: (r) =>
                      [
                        "new_failure",
                        "fixed",
                        "still_failing",
                        "added",
                        "removed",
                        "still_passing",
                      ].indexOf(r.change),
                    render: (r) => (
                      <Badge tone={CHANGE[r.change].tone}>
                        {CHANGE[r.change].label}
                      </Badge>
                    ),
                  },
                  { key: "test", header: "Test", mono: true },
                  {
                    key: "old_status",
                    header: "Before",
                    render: (r) =>
                      r.old_status ? (
                        <StatusBadge status={r.old_status} />
                      ) : (
                        "–"
                      ),
                  },
                  {
                    key: "new_status",
                    header: "Now",
                    render: (r) =>
                      r.new_status ? (
                        <StatusBadge status={r.new_status} />
                      ) : (
                        "–"
                      ),
                  },
                  {
                    key: "sig",
                    header: "Signature",
                    wrap: true,
                    value: (r) => r.new_signature || r.old_signature,
                    render: (r) => (
                      <span className="font-mono text-[12.5px]">
                        {r.new_signature || r.old_signature || "–"}
                        {r.signature_changed && (
                          <Badge tone="warn" className="ml-2">
                            signature changed
                          </Badge>
                        )}
                      </span>
                    ),
                  },
                ]}
              />
            </Card>
          </>
        )
      )}
    </>
  );
}

function TimingCompare() {
  const [oldF, setOldF] = useState<SourceFile[] | null>(null),
    [newF, setNewF] = useState<SourceFile[] | null>(null);
  const [show, setShow] = useState([
    "new_violation",
    "fixed",
    "degraded",
    "improved",
    "added",
    "removed",
  ]);
  const { data, loading, error } = useAnalysis<TimResult>(
    "/api/compare/timing",
    oldF && newF ? { old: oldF[0], new: newF[0] } : null,
  );
  const v = data && !data.error ? VERDICT[data.verdict] : null;
  return (
    <>
      <Card className="mb-6">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr]">
          <SidePicker title="Before (e.g. pre-ECO)">
            <FileSource
              label="Report"
              examples={["sta_report.rpt"]}
              wsKinds={["timing"]}
              onChange={setOldF}
            />
          </SidePicker>
          <ArrowRight className="hidden size-5 self-center text-faint lg:block" />
          <SidePicker title="After (e.g. post-ECO)">
            <FileSource
              label="Report"
              examples={["sta_report_eco.rpt"]}
              wsKinds={["timing"]}
              onChange={setNewF}
            />
          </SidePicker>
        </div>
      </Card>
      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!oldF || !newF ? (
        <EmptyState
          icon={GitCompareArrows}
          title="Pick both reports"
          text="Load two timing reports of the same design to see what changed."
        />
      ) : loading && !data ? (
        <LoadingBlock label="Comparing…" />
      ) : data?.error ? (
        <Alert tone="bad">{data.error}</Alert>
      ) : (
        data &&
        v && (
          <>
            <Alert tone={v.tone} title={`Verdict: ${v.title}`}>
              {v.text}
            </Alert>
            <div className="mb-6 grid gap-4 md:grid-cols-2">
              {data.checks.map((c) => (
                <Card
                  key={c.check}
                  title={<span className="capitalize">{c.check} timing</span>}
                  bodyClass="grid grid-cols-3 gap-4 p-5"
                >
                  {[
                    ["WNS (ns)", c.old_wns, c.new_wns, c.delta_wns],
                    ["TNS (ns)", c.old_tns, c.new_tns, c.delta_tns],
                  ].map(([label, a, b, d]) => (
                    <div
                      key={label as string}
                      className="col-span-3 grid grid-cols-3 items-baseline gap-4 sm:col-span-3"
                    >
                      <div className="text-[12px] font-semibold tracking-wide text-faint uppercase">
                        {label as string}
                      </div>
                      <div className="font-mono text-[15px] tabular-nums">
                        <span className="text-muted">{f3(a as number)}</span> →{" "}
                        <b>{f3(b as number)}</b>
                      </div>
                      <div className="text-right">
                        <Delta v={d as number | null} />
                      </div>
                    </div>
                  ))}
                  <div className="col-span-3 flex items-center justify-between border-t border-line pt-3 text-[13px]">
                    <span className="text-muted">Violating paths</span>
                    <span className="font-semibold tabular-nums">
                      {c.old_violations} → {c.new_violations}
                    </span>
                  </div>
                </Card>
              ))}
            </div>
            <KpiGrid
              items={[
                {
                  label: "New violations",
                  value: data.counts.new_violation,
                  tone: data.counts.new_violation ? "bad" : "good",
                },
                {
                  label: "Fixed",
                  value: data.counts.fixed,
                  tone: data.counts.fixed ? "good" : "neutral",
                },
                {
                  label: "Degraded",
                  value: data.counts.degraded,
                  tone: data.counts.degraded ? "warn" : "good",
                },
                {
                  label: "Improved",
                  value: data.counts.improved,
                  tone: data.counts.improved ? "good" : "neutral",
                },
                { label: "Unchanged", value: data.counts.unchanged },
              ]}
            />
            <Card
              title="Endpoints"
              subtitle="Worst slack per endpoint, before vs after"
              bodyClass="p-4"
            >
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <Chips
                  selected={show}
                  onChange={setShow}
                  options={[
                    "new_violation",
                    "fixed",
                    "degraded",
                    "improved",
                    "unchanged",
                    "added",
                    "removed",
                  ].map((c) => ({
                    value: c,
                    label: CHANGE[c]?.label ?? c,
                    tone: CHANGE[c]?.tone,
                    count: data.counts[c],
                  }))}
                />
                <button
                  className="text-[13px] font-medium text-brand hover:underline"
                  onClick={() =>
                    downloadText(
                      "timing_compare.csv",
                      toCSV(data.rows),
                      "text/csv",
                    )
                  }
                >
                  Export CSV
                </button>
              </div>
              <DataTable
                rows={data.rows.filter((r) => show.includes(r.change))}
                searchable
                initialSort={{ key: "delta", dir: "asc" }}
                columns={[
                  {
                    key: "change",
                    header: "Change",
                    render: (r) => (
                      <Badge tone={CHANGE[r.change]?.tone ?? "neutral"}>
                        {CHANGE[r.change]?.label ?? r.change}
                      </Badge>
                    ),
                  },
                  { key: "check", header: "Check" },
                  { key: "endpoint", header: "Endpoint", mono: true },
                  {
                    key: "old_slack",
                    header: "Slack before",
                    align: "right",
                    render: (r) => (
                      <span
                        className={(r.old_slack ?? 0) < 0 ? "text-bad" : ""}
                      >
                        {f3(r.old_slack)}
                      </span>
                    ),
                  },
                  {
                    key: "new_slack",
                    header: "Slack now",
                    align: "right",
                    render: (r) => (
                      <span
                        className={cx(
                          "font-semibold",
                          (r.new_slack ?? 0) < 0 && "text-bad",
                        )}
                      >
                        {f3(r.new_slack)}
                      </span>
                    ),
                  },
                  {
                    key: "delta",
                    header: "Delta",
                    align: "right",
                    render: (r) => <Delta v={r.delta} />,
                  },
                ]}
              />
            </Card>
          </>
        )
      )}
    </>
  );
}

export default function Compare() {
  const [mode, setMode] = useState<"regress" | "timing">("regress");
  return (
    <>
      <PageHeader
        area="Tracking"
        title="Compare Runs"
        icon={GitCompareArrows}
        description="See exactly what changed between two runs: new failures and fixes between regressions, or better/worse paths between timing reports (before and after an ECO)."
        actions={
          <Segmented
            value={mode}
            onChange={setMode}
            options={[
              { value: "regress", label: "Regression", icon: ClipboardCheck },
              { value: "timing", label: "Timing", icon: Timer },
            ]}
          />
        }
      />
      {mode === "regress" ? <RegressionCompare /> : <TimingCompare />}
    </>
  );
}
