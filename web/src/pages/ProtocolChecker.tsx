import { useState } from "react";
import { BookOpen, Bug, ListOrdered, Radar } from "lucide-react";
import { initialExample, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { ReportButton, type Report } from "../components/ReportButton";
import { DataTable, type Column } from "../components/DataTable";
import { Alert, Card, Chips, EmptyState, Field, KpiGrid, LoadingBlock, NumberInput, PageHeader, Segmented, Select, StatusBadge, Tabs, type KpiItem } from "../components/ui";

type Violation = { rule: string; severity: "ERROR" | "WARNING"; cycle: number | null; time: number; message: string };
type Itf = {
  protocol: string; interface: string; clock: string | null; signals: Record<string, string>; timescale: string;
  violations: Violation[]; transactions: Record<string, unknown>[]; stats: Record<string, number | null>;
  rules: { rule: string; severity: string; description: string }[]; decoded_text?: string; mode?: number; error?: string;
};
type Result = { interfaces: Itf[]; timescale: string; supported: string[] };

const EXAMPLES = {
  apb: "protocols/apb_demo.vcd",
  ahb: "protocols/ahb_lite_demo.vcd",
  axis: "protocols/axi_stream_demo.vcd",
  spi: "protocols/spi_demo.vcd",
  i2c: "protocols/i2c_demo.vcd",
  uart: "protocols/uart_demo.vcd",
} as const;

/** Columns shown first for each protocol; any other fields follow. */
const COLUMNS: Record<string, string[]> = {
  APB: ["kind", "addr", "data", "waits", "resp", "start_cycle"],
  "AHB-Lite": ["kind", "trans", "burst", "addr", "data", "size", "resp", "start_cycle"],
  "AXI-Stream": ["start_cycle", "beats", "bytes", "data", "latency"],
  SPI: ["index", "bits", "mosi", "miso", "text", "start_time"],
  I2C: ["kind", "addr", "addr_ack", "data", "acks", "text", "stop", "start_time"],
  UART: ["start_time", "value", "char", "framing"],
};
const HIDE = new Set(["end_time", "end_cycle", "tid", "tdest", "repeated", "nbytes"]);
const LABEL: Record<string, string> = {
  kind: "Type", addr: "Address", data: "Data", waits: "Wait states", resp: "Response", start_cycle: "Cycle", trans: "HTRANS",
  burst: "Burst", size: "Bytes", beats: "Beats", bytes: "Bytes", latency: "Cycles", index: "#", bits: "Bits", mosi: "MOSI",
  miso: "MISO", text: "ASCII", start_time: "Time", addr_ack: "Addr ACK", acks: "Data ACKs", stop: "STOP", value: "Byte", char: "Char",
  framing: "Stop bit",
};

function show(v: unknown): string {
  if (v == null) return "–";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.join(" ");
  return String(v);
}

function statKpis(itf: Itf): KpiItem[] {
  const s = itf.stats;
  const out: KpiItem[] = [
    { label: "Protocol", value: itf.protocol, note: itf.interface, tone: "info" },
    { label: "Errors", value: s.errors ?? 0, note: s.errors ? "protocol violations" : "none", tone: s.errors ? "bad" : "good" },
    { label: "Warnings", value: s.warnings ?? 0, note: s.warnings ? "review" : "none", tone: s.warnings ? "warn" : "good" },
  ];
  const p = itf.protocol;
  if (p === "APB" || p === "AHB-Lite") out.push({ label: "Transfers", value: (s.writes ?? 0) + (s.reads ?? 0), note: `${s.writes ?? 0} writes · ${s.reads ?? 0} reads` });
  if (p === "APB") out.push({ label: "Avg. wait states", value: s.avg_wait_states ?? "–", note: `${s.cycles} cycles` });
  if (p === "AHB-Lite") out.push({ label: "Bursts", value: s.bursts ?? 0, note: `${s.cycles} cycles` });
  if (p === "AXI-Stream") {
    out.push({ label: "Packets", value: s.packets ?? 0, note: `${s.beats} beats · avg ${s.avg_packet_beats ?? "–"}` });
    out.push({ label: "Throughput", value: s.throughput_MBps != null ? `${s.throughput_MBps} MB/s` : "–", note: `back-pressure ${Math.round((s.backpressure ?? 0) * 100)}%` });
  }
  if (p === "SPI") {
    out.push({ label: "Frames", value: s.frames ?? 0, note: `${s.bytes} bytes` });
    out.push({ label: "SPI mode", value: s.mode ?? "–", note: `CPOL=${s.cpol} (from idle level), CPHA=0` });
  }
  if (p === "I2C") out.push({ label: "Transactions", value: s.transactions ?? 0, note: `${s.bytes} data bytes · ${s.nacks} NACK` });
  if (p === "UART") {
    out.push({ label: "Bytes", value: s.bytes ?? 0, note: `${s.framing_errors} framing error(s)` });
    out.push({ label: "Baud rate", value: s.baud ? s.baud.toLocaleString("en-US") : "–", note: `bit = ${s.bit_time} ${itf.timescale} (auto-detected)` });
  }
  return out;
}

export default function ProtocolChecker() {
  const [example, setExample] = useState<keyof typeof EXAMPLES>(() => initialExample("apb", EXAMPLES));
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [timeout, setTimeoutCycles] = useState(16);
  const [pick, setPick] = useState(0);
  const [tab, setTab] = useState("violations");
  const [sev, setSev] = useState<string[]>(["ERROR", "WARNING"]);
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>("/api/verif/protocols", file ? { ...file, timeout: Math.max(1, timeout) } : null);
  const itf = data?.interfaces[Math.min(pick, (data?.interfaces.length ?? 1) - 1)];

  const columns: Column<Record<string, unknown>>[] = itf
    ? (() => {
        const first = COLUMNS[itf.protocol] ?? [];
        const keys = [...first, ...Object.keys(itf.transactions[0] ?? {}).filter((k) => !first.includes(k) && !HIDE.has(k))];
        return keys.filter((k) => itf.transactions.some((t) => k in t)).map((k) => ({
          key: k,
          header: LABEL[k] ?? k,
          mono: ["addr", "data", "mosi", "miso", "value", "text", "char"].includes(k),
          wrap: k === "data",
          align: ["waits", "start_cycle", "beats", "bytes", "latency", "index", "bits", "start_time", "size"].includes(k) ? ("right" as const) : undefined,
          value: (r: Record<string, unknown>) => (typeof r[k] === "number" ? (r[k] as number) : show(r[k])),
          render: (r: Record<string, unknown>) => {
            const v = r[k];
            if ((k === "resp" && v !== "OKAY") || (k === "framing" && v === false) || (k === "addr_ack" && v === false))
              return <span className="font-semibold text-bad">{k === "framing" ? "0 (error)" : show(v)}</span>;
            if (k === "framing") return "1";
            return show(v);
          },
        }));
      })()
    : [];

  const report: Report | null = itf && file ? {
    tool: "Protocol Checker",
    title: `${itf.protocol} interface ${itf.interface}`,
    files: [file.name],
    verdict: itf.stats.errors ? { tone: "bad", text: `${itf.stats.errors} protocol error(s), ${itf.stats.warnings} warning(s)` } : itf.stats.warnings ? { tone: "warn", text: `No errors, ${itf.stats.warnings} warning(s)` } : { tone: "good", text: `${itf.protocol} traffic follows the protocol` },
    kpis: statKpis(itf).map((k) => ({ label: k.label, value: String(k.value), note: typeof k.note === "string" ? k.note : undefined, tone: k.tone })),
    sections: [
      ...(itf.decoded_text ? [{ title: "Decoded text", kind: "text" as const, text: itf.decoded_text, mono: true }] : []),
      { title: "Violations", kind: "table", columns: [{ key: "time", label: `Time (${itf.timescale})`, align: "right" }, { key: "severity", label: "Severity" }, { key: "rule", label: "Rule" }, { key: "message", label: "What happened" }], rows: itf.violations },
      { title: "Transactions", kind: "table", limit: 100, columns: columns.map((c) => ({ key: c.key, label: c.header })), rows: itf.transactions },
    ],
  } : null;

  return (
    <>
      <PageHeader actions={<ReportButton report={report} />} area="Verification" title="Protocol Checker" icon={Radar}
        description="Load a simulation waveform (VCD): APB, AHB-Lite, AXI-Stream, SPI, I2C and UART interfaces are found by their signal names, checked against the protocol rules and decoded into readable transfers. For full AXI4 use the AXI Protocol Checker." />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="text-[13px] font-medium text-muted">Example</span>
              <Segmented size="sm" value={example} onChange={(v) => { setExample(v); setPick(0); }} options={[
                { value: "apb", label: "APB" }, { value: "ahb", label: "AHB-Lite" }, { value: "axis", label: "AXI-Stream" },
                { value: "spi", label: "SPI" }, { value: "i2c", label: "I2C" }, { value: "uart", label: "UART" },
              ]} />
            </div>
            <FileSource label="VCD waveform" examples={[EXAMPLES[example]]} accept=".vcd" wsKinds={["vcd"]} onChange={(f) => { setFiles(f); setPick(0); }} />
          </div>
          <Field label="Timeout (cycles)" hint="Ready/wait signals held longer than this are reported." className="w-44">
            <NumberInput value={timeout} onChange={setTimeoutCycles} min={1} />
          </Field>
        </div>
      </Card>

      {error && <Alert tone="bad" title="Request failed">{error}</Alert>}
      {!file ? <EmptyState icon={Radar} title="No waveform yet" text="Upload a VCD from your simulator, or pick one of the examples." />
        : loading && !data ? <LoadingBlock />
        : data && (data.interfaces.length === 0 ? (
          <Alert tone="warn" title="No supported interface found">
            Signals are recognized by name: APB psel/penable/paddr, AHB-Lite htrans/haddr/hready, AXI-Stream tvalid/tdata, SPI sclk + mosi/miso
            (+ cs_n), I2C scl + sda, UART tx/rx/txd/rxd. Any prefix is fine (e.g. <code className="font-mono">m_apb_psel</code>).
          </Alert>
        ) : itf && (
          <>
            {data.interfaces.length > 1 && (
              <div className="mb-4 w-80">
                <Select value={String(pick)} onChange={(v) => setPick(Number(v))}
                  options={data.interfaces.map((i, k) => ({ value: String(k), label: `${i.protocol}: ${i.interface}` }))} />
              </div>
            )}
            {itf.error && <Alert tone="bad" title="Cannot check this interface">{itf.error}</Alert>}
            <KpiGrid items={statKpis(itf)} />
            {itf.decoded_text != null && itf.decoded_text !== "" && (
              <Card title="Decoded text" subtitle="Bytes as ASCII; · marks non-printable bytes" className="mb-6">
                <pre className="font-mono text-[14px] whitespace-pre-wrap break-all">{itf.decoded_text}</pre>
              </Card>
            )}
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "violations", label: "Violations", icon: Bug, count: itf.violations.length },
              { id: "tx", label: "Transactions", icon: ListOrdered, count: itf.transactions.length },
              { id: "rules", label: "Rules", icon: BookOpen, count: itf.rules.length },
            ]} />
            {tab === "violations" && (itf.violations.length === 0 ? <Alert tone="good" title="No protocol violations">Every transfer follows the {itf.protocol} rules.</Alert> : (
              <Card bodyClass="p-4">
                <div className="mb-4">
                  <Chips selected={sev} onChange={setSev} options={[
                    { value: "ERROR", label: "Errors", tone: "bad", count: itf.stats.errors ?? 0 },
                    { value: "WARNING", label: "Warnings", tone: "warn", count: itf.stats.warnings ?? 0 },
                  ]} />
                </div>
                <DataTable rows={itf.violations.filter((v) => sev.includes(v.severity))} initialSort={{ key: "time", dir: "asc" }} columns={[
                  { key: "time", header: `Time (${itf.timescale})`, align: "right" },
                  { key: "cycle", header: "Cycle", align: "right", render: (v) => v.cycle ?? "–" },
                  { key: "severity", header: "Severity", render: (v) => <StatusBadge status={v.severity} /> },
                  { key: "rule", header: "Rule", mono: true },
                  { key: "message", header: "What happened", wrap: true },
                ]} />
              </Card>
            ))}
            {tab === "tx" && (
              <Card bodyClass="p-4">
                <DataTable rows={itf.transactions} columns={columns} searchable empty="No transfers decoded" />
              </Card>
            )}
            {tab === "rules" && (
              <Card bodyClass="p-4">
                <DataTable rows={itf.rules} columns={[
                  { key: "severity", header: "Severity", render: (r) => <StatusBadge status={r.severity} /> },
                  { key: "rule", header: "Rule", mono: true },
                  { key: "description", header: "Checks that", wrap: true },
                ]} />
              </Card>
            )}
          </>
        ))}
    </>
  );
}
