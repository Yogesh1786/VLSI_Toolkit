import { Fragment, useState } from "react";
import {
  ArrowLeftRight,
  BookOpen,
  ChartGantt,
  ChevronDown,
  ChevronRight,
  Gauge,
  ListOrdered,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useAnalysis, type SourceFile, initialExample } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { AxiTimeline } from "../components/charts";
import {
  Alert,
  Badge,
  Card,
  Chips,
  EmptyState,
  Field,
  KpiGrid,
  LoadingBlock,
  NumberInput,
  PageHeader,
  Segmented,
  Select,
  StatusBadge,
  Tabs,
} from "../components/ui";
import { cx, downloadText, toCSV } from "../lib/format";

type Violation = {
  rule: string;
  severity: "ERROR" | "WARNING";
  channel: string;
  cycle: number;
  time: number;
  message: string;
};
type Txn = {
  kind: "WRITE" | "READ";
  id: number | null;
  addr: string;
  length: number;
  size: number | null;
  burst: string;
  beats: number;
  data: string[];
  strb: (string | null)[];
  resp: string | null;
  status: string;
  start_cycle: number;
  end_cycle: number | null;
  start_time: number;
  end_time: number | null;
  latency: number | null;
  waited: number;
  request_cycle: number;
};
type Stats = {
  count: number;
  completed: number;
  beats: number;
  bytes: number;
  bandwidth_MBps: number | null;
  latency_avg: number | null;
  latency_min: number | null;
  latency_max: number | null;
  errors: number;
};
type Itf = {
  error?: string;
  interface: string;
  kind: string;
  clock: string;
  reset: string | null;
  data_width: number | null;
  addr_width: number | null;
  clock_period: number;
  timescale: string;
  cycles: number;
  active_cycles: number;
  signals: string[];
  write: Stats;
  read: Stats;
  channels: {
    channel: string;
    handshakes: number;
    stall_cycles: number;
    utilization: number;
  }[];
  violations: Violation[];
  transactions: Txn[];
};
type Result = {
  error?: string;
  interfaces: Itf[];
  rules: { rule: string; severity: string; description: string }[];
};

const EXAMPLES = {
  buggy: "axi/axi_buggy.vcd",
  clean: "axi/axi_clean.vcd",
} as const;
const STATUS_TONE: Record<string, "good" | "bad" | "warn"> = {
  OKAY: "good",
  EXOKAY: "good",
  SLVERR: "bad",
  DECERR: "bad",
  NO_RESPONSE: "warn",
};

export default function AxiChecker() {
  const [example, setExample] = useState<keyof typeof EXAMPLES>(() => initialExample("buggy", EXAMPLES));
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [timeout, setTimeoutCycles] = useState(16);
  const [itfName, setItfName] = useState("");
  const [tab, setTab] = useState("violations");
  const [sev, setSev] = useState<string[]>(["ERROR", "WARNING"]);
  const [kinds, setKinds] = useState<string[]>(["WRITE", "READ"]);
  const [open, setOpen] = useState<number | null>(null);
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>(
    "/api/verif/axi",
    file ? { ...file, timeout: Math.max(1, timeout) } : null,
  );
  const itfs = data?.interfaces ?? [];
  const itf = itfs.find((i) => i.interface === itfName) ?? itfs[0];
  const errors =
    itf?.violations.filter((v) => v.severity === "ERROR").length ?? 0;
  const warnings = (itf?.violations.length ?? 0) - errors;
  const shownTxns = itf
    ? itf.transactions
        .map((t, i) => ({ ...t, n: i + 1 }))
        .filter((t) => kinds.includes(t.kind))
    : [];

  return (
    <>
      <PageHeader
        area="Verification"
        title="AXI Protocol Checker"
        icon={ArrowLeftRight}
        description="Load a simulation waveform (VCD): AXI interfaces are found automatically, every handshake is checked against the AXI rules, and the raw signals are turned into a readable list of transactions."
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="text-[13px] font-medium text-muted">
                Example
              </span>
              <Segmented
                size="sm"
                value={example}
                onChange={setExample}
                options={[
                  { value: "buggy", label: "Traffic with planted bugs" },
                  { value: "clean", label: "Clean traffic" },
                ]}
              />
            </div>
            <FileSource
              label="VCD waveform"
              examples={[EXAMPLES[example]]}
              accept=".vcd"
              onChange={setFiles}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:w-[380px]">
            <Field
              label="READY timeout (cycles)"
              hint="Warn when VALID waits longer than this for READY"
            >
              <NumberInput
                value={timeout}
                onChange={setTimeoutCycles}
                min={1}
              />
            </Field>
            {itfs.length > 1 && (
              <Field label="Interface">
                <Select
                  value={itf?.interface ?? ""}
                  onChange={setItfName}
                  options={itfs.map((i) => ({
                    value: i.interface,
                    label: `${i.interface}* (${i.kind})`,
                  }))}
                />
              </Field>
            )}
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
          icon={ArrowLeftRight}
          title="No waveform yet"
          text="Upload a VCD that contains AXI signals (e.g. s_axi_awvalid, s_axi_wdata …)."
        />
      ) : loading && !data ? (
        <LoadingBlock label="Checking protocol…" />
      ) : data?.error ? (
        <Alert tone="bad" title="No AXI interface found">
          {data.error}
        </Alert>
      ) : itf?.error ? (
        <Alert tone="bad">{itf.error}</Alert>
      ) : (
        itf && (
          <>
            <div
              className={cx(
                "mb-6 flex flex-wrap items-center gap-4 rounded-xl border px-5 py-4",
                errors
                  ? "border-bad/30 bg-bad/6"
                  : warnings
                    ? "border-warn/35 bg-warn/8"
                    : "border-good/30 bg-good/6",
              )}
            >
              {errors || warnings ? (
                <ShieldAlert
                  className={cx("size-8", errors ? "text-bad" : "text-warn")}
                />
              ) : (
                <ShieldCheck className="size-8 text-good" />
              )}
              <div className="min-w-0 flex-1">
                <div className="text-[17px] font-semibold">
                  {errors
                    ? `Protocol check FAILED: ${errors} error${errors > 1 ? "s" : ""}`
                    : warnings
                      ? "Protocol rules OK, with warnings"
                      : "Protocol check PASSED"}
                  {warnings > 0 && (
                    <span className="font-normal text-muted">
                      {" "}
                      · {warnings} warning{warnings > 1 ? "s" : ""}
                    </span>
                  )}
                </div>
                <div className="text-[13.5px] text-muted">
                  <span className="font-mono">{itf.interface}*</span> ·{" "}
                  {itf.kind} · {itf.data_width}-bit data · {itf.addr_width}-bit
                  address · clock <span className="font-mono">{itf.clock}</span>{" "}
                  ({itf.clock_period} {itf.timescale.replace(/^1/, "")}) ·{" "}
                  {itf.cycles} cycles
                </div>
              </div>
            </div>

            <KpiGrid
              items={[
                {
                  label: "Writes",
                  value: itf.write.count,
                  note: `${itf.write.bytes} bytes · ${itf.write.errors} error resp`,
                  tone: itf.write.errors ? "bad" : "neutral",
                },
                {
                  label: "Reads",
                  value: itf.read.count,
                  note: `${itf.read.bytes} bytes · ${itf.read.errors} error resp`,
                  tone: itf.read.errors ? "bad" : "neutral",
                },
                {
                  label: "Violations",
                  value: itf.violations.length,
                  note: `${errors} errors · ${warnings} warnings`,
                  tone: errors ? "bad" : warnings ? "warn" : "good",
                },
                {
                  label: "Avg latency",
                  value: `${itf.write.latency_avg ?? "–"} / ${itf.read.latency_avg ?? "–"}`,
                  note: "write / read, cycles",
                  tone: "info",
                },
                {
                  label: "Bandwidth",
                  value: `${((itf.write.bandwidth_MBps ?? 0) + (itf.read.bandwidth_MBps ?? 0)).toFixed(1)} MB/s`,
                  note: `W ${itf.write.bandwidth_MBps ?? 0} · R ${itf.read.bandwidth_MBps ?? 0}`,
                },
              ]}
            />

            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                {
                  id: "violations",
                  label: "Violations",
                  icon: ShieldAlert,
                  count: itf.violations.length,
                },
                {
                  id: "txns",
                  label: "Transactions",
                  icon: ListOrdered,
                  count: itf.transactions.length,
                },
                { id: "timeline", label: "Timeline", icon: ChartGantt },
                { id: "perf", label: "Channel performance", icon: Gauge },
                {
                  id: "rules",
                  label: "Rules",
                  icon: BookOpen,
                  count: data?.rules.length ?? 0,
                },
              ]}
            />

            {tab === "violations" &&
              (itf.violations.length === 0 ? (
                <Alert tone="good" title="No protocol violations">
                  Every handshake followed the AXI rules: VALID stable until
                  READY, payload stable, correct LAST beats, no 4 KB crossings,
                  every request answered.
                </Alert>
              ) : (
                <Card bodyClass="p-4">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <Chips
                      selected={sev}
                      onChange={setSev}
                      options={[
                        {
                          value: "ERROR",
                          label: "Errors",
                          tone: "bad",
                          count: errors,
                        },
                        {
                          value: "WARNING",
                          label: "Warnings",
                          tone: "warn",
                          count: warnings,
                        },
                      ]}
                    />
                    <button
                      className="text-[13px] font-medium text-brand hover:underline"
                      onClick={() =>
                        downloadText(
                          "axi_violations.csv",
                          toCSV(itf.violations),
                          "text/csv",
                        )
                      }
                    >
                      Export CSV
                    </button>
                  </div>
                  <DataTable
                    rows={itf.violations.filter((v) =>
                      sev.includes(v.severity),
                    )}
                    columns={[
                      { key: "cycle", header: "Cycle", align: "right" },
                      {
                        key: "time",
                        header: `Time (${itf.timescale.replace(/^1/, "")})`,
                        align: "right",
                      },
                      {
                        key: "severity",
                        header: "Severity",
                        render: (v) => <StatusBadge status={v.severity} />,
                      },
                      { key: "rule", header: "Rule", mono: true },
                      {
                        key: "channel",
                        header: "Channel",
                        render: (v) => <Badge tone="info">{v.channel}</Badge>,
                      },
                      { key: "message", header: "What happened", wrap: true },
                    ]}
                  />
                  <p className="mt-3 text-[13px] text-muted">
                    Tip: open the same VCD in the Waveform Viewer and zoom to
                    the cycle × {itf.clock_period}{" "}
                    {itf.timescale.replace(/^1/, "")} to see the signals around
                    each violation.
                  </p>
                </Card>
              ))}

            {tab === "txns" && (
              <Card bodyClass="p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <Chips
                    selected={kinds}
                    onChange={setKinds}
                    options={[
                      {
                        value: "WRITE",
                        label: "Writes",
                        count: itf.write.count,
                      },
                      { value: "READ", label: "Reads", count: itf.read.count },
                    ]}
                  />
                  <button
                    className="text-[13px] font-medium text-brand hover:underline"
                    onClick={() =>
                      downloadText(
                        "axi_transactions.csv",
                        toCSV(
                          itf.transactions.map((t) => ({
                            ...t,
                            data: t.data.join(" "),
                            strb: t.strb.join(" "),
                          })),
                        ),
                        "text/csv",
                      )
                    }
                  >
                    Export CSV
                  </button>
                </div>
                <div className="overflow-auto rounded-lg border border-line">
                  <table className="w-full border-collapse text-[13.5px]">
                    <thead className="bg-surface-2 text-[12px] text-muted">
                      <tr>
                        {[
                          "",
                          "#",
                          "Kind",
                          "ID",
                          "Address",
                          "Beats",
                          "Burst",
                          "First data",
                          "Response",
                          "Cycles",
                          "Addr wait",
                          "Latency",
                        ].map((h) => (
                          <th
                            key={h}
                            className="border-b border-line px-3 py-2.5 text-left font-semibold whitespace-nowrap"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {shownTxns.map((t) => (
                        <Fragment key={t.n}>
                          <tr
                            className="cursor-pointer border-b border-line hover:bg-surface-2"
                            onClick={() => setOpen(open === t.n ? null : t.n)}
                          >
                            <td className="px-2 text-faint">
                              {open === t.n ? (
                                <ChevronDown className="size-4" />
                              ) : (
                                <ChevronRight className="size-4" />
                              )}
                            </td>
                            <td className="px-3 py-2 tabular-nums text-faint">
                              {t.n}
                            </td>
                            <td className="px-3 py-2">
                              <Badge
                                tone={t.kind === "WRITE" ? "info" : "neutral"}
                              >
                                {t.kind}
                              </Badge>
                            </td>
                            <td className="px-3 py-2 font-mono">
                              {t.id ?? "–"}
                            </td>
                            <td className="px-3 py-2 font-mono font-semibold">
                              {t.addr}
                            </td>
                            <td
                              className={cx(
                                "px-3 py-2 tabular-nums",
                                t.beats !== t.length &&
                                  "font-semibold text-bad",
                              )}
                            >
                              {t.beats}/{t.length}
                            </td>
                            <td className="px-3 py-2 text-muted">
                              {t.burst} · {t.size ?? "?"}B
                            </td>
                            <td className="px-3 py-2 font-mono text-[12.5px]">
                              {t.data[0] ?? "–"}
                              {t.data.length > 1 && (
                                <span className="text-faint">
                                  {" "}
                                  +{t.data.length - 1}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <Badge tone={STATUS_TONE[t.status] ?? "neutral"}>
                                {t.status}
                              </Badge>
                            </td>
                            <td className="px-3 py-2 font-mono text-[12.5px] text-muted">
                              {t.start_cycle} → {t.end_cycle ?? "…"}
                            </td>
                            <td
                              className={cx(
                                "px-3 py-2 text-right tabular-nums",
                                t.waited > 4 && "font-semibold text-warn",
                              )}
                            >
                              {t.waited || "–"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {t.latency ?? "–"}
                            </td>
                          </tr>
                          {open === t.n && (
                            <tr className="border-b border-line bg-surface-2">
                              <td colSpan={12} className="px-6 py-3">
                                {t.data.length ? (
                                  <div className="flex flex-wrap gap-2">
                                    {t.data.map((d, k) => (
                                      <span
                                        key={k}
                                        className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-[12px]"
                                      >
                                        <span className="text-faint">
                                          beat {k + 1} · 0x
                                          {(
                                            (parseInt(t.addr, 16) || 0) +
                                            k * (t.size ?? 4)
                                          )
                                            .toString(16)
                                            .toUpperCase()}{" "}
                                        </span>
                                        {d}
                                        {t.strb[k] && (
                                          <span className="text-faint">
                                            {" "}
                                            strb {t.strb[k]}
                                          </span>
                                        )}
                                      </span>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-[13px] text-muted">
                                    No data beats were transferred.
                                  </span>
                                )}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-[13px] text-muted">
                  Click a row to see every data beat with its address. Latency =
                  cycles from the address handshake to the final response.
                </p>
              </Card>
            )}

            {tab === "timeline" && (
              <Card
                title="Transaction timeline"
                subtitle="Each bar runs from the address handshake to the final response; triangles mark violations"
              >
                <AxiTimeline
                  cycles={itf.cycles}
                  txns={itf.transactions}
                  marks={itf.violations}
                  onSelect={(i) => {
                    setOpen(i + 1);
                    setTab("txns");
                  }}
                />
                <div className="mt-3 flex flex-wrap gap-4 text-[12.5px] text-muted">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-5 rounded-sm bg-good" />
                    OKAY
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-5 rounded-sm bg-bad" />
                    SLVERR / DECERR
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-5 rounded-sm border border-dashed border-warn bg-warn/25" />
                    no response
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-1.5 w-5 rounded-sm bg-warn/50" />
                    waiting for READY
                  </span>
                  <span>Click a bar to open the transaction.</span>
                </div>
              </Card>
            )}

            {tab === "perf" && (
              <div className="grid gap-5 lg:grid-cols-2">
                <Card
                  title="Channels"
                  subtitle="Handshakes, and cycles where VALID waited for READY"
                  bodyClass="p-4"
                >
                  <DataTable
                    rows={itf.channels}
                    columns={[
                      {
                        key: "channel",
                        header: "Channel",
                        render: (c) => <Badge tone="info">{c.channel}</Badge>,
                      },
                      {
                        key: "handshakes",
                        header: "Handshakes",
                        align: "right",
                      },
                      {
                        key: "stall_cycles",
                        header: "Stall cycles",
                        align: "right",
                        render: (c) => (
                          <span
                            className={
                              c.stall_cycles ? "font-semibold text-warn" : ""
                            }
                          >
                            {c.stall_cycles}
                          </span>
                        ),
                      },
                      {
                        key: "utilization",
                        header: "Utilization",
                        render: (c) => (
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-surface-3">
                              <div
                                className="h-full rounded-full bg-brand"
                                style={{
                                  width: `${Math.min(100, c.utilization * 100)}%`,
                                }}
                              />
                            </div>
                            <span className="tabular-nums">
                              {(c.utilization * 100).toFixed(1)}%
                            </span>
                          </div>
                        ),
                      },
                    ]}
                  />
                </Card>
                <Card title="Latency (cycles)">
                  <div className="grid grid-cols-2 gap-5">
                    {(["write", "read"] as const).map((k) => (
                      <div
                        key={k}
                        className="rounded-lg border border-line p-4"
                      >
                        <div className="mb-2 text-[12px] font-semibold tracking-wide text-faint uppercase">
                          {k}
                        </div>
                        {[
                          ["min", itf[k].latency_min],
                          ["avg", itf[k].latency_avg],
                          ["max", itf[k].latency_max],
                        ].map(([l, v]) => (
                          <div
                            key={l as string}
                            className="flex justify-between py-1 text-[14px]"
                          >
                            <span className="text-muted">{l as string}</span>
                            <b className="tabular-nums">{v ?? "–"}</b>
                          </div>
                        ))}
                        <div className="mt-2 border-t border-line pt-2 text-[13px] text-muted">
                          {itf[k].completed}/{itf[k].count} completed ·{" "}
                          {itf[k].beats} beats
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            )}

            {tab === "rules" && (
              <Card bodyClass="p-4">
                <DataTable
                  rows={(data?.rules ?? []).map((r) => ({
                    ...r,
                    hits: itf.violations.filter((v) => v.rule === r.rule)
                      .length,
                  }))}
                  columns={[
                    {
                      key: "severity",
                      header: "Severity",
                      render: (r) => <StatusBadge status={r.severity} />,
                    },
                    { key: "rule", header: "Rule", mono: true },
                    {
                      key: "hits",
                      header: "Hits",
                      align: "right",
                      render: (r) => (
                        <span
                          className={
                            r.hits ? "font-semibold text-bad" : "text-faint"
                          }
                        >
                          {r.hits}
                        </span>
                      ),
                    },
                    {
                      key: "description",
                      header: "What it checks",
                      wrap: true,
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
