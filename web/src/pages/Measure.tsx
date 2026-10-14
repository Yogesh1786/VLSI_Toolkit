import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartLine, Table } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
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
  Select,
  Tabs,
} from "../components/ui";
import { downloadText, eng, PALETTE, toCSV } from "../lib/format";

type Meas = Record<string, number | null>;
type Result = {
  error?: string;
  signals: string[];
  selected: string[];
  ref: string | null;
  results: Record<string, Meas>;
  labels: { key: string; label: string; unit: string }[];
  plot: Record<string, number>[];
};

export default function Measure() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [signals, setSignals] = useState<string[]>(["v(out)"]);
  const [ref, setRef] = useState("v(in)");
  const [vdd, setVdd] = useState(1.8);
  const [tab, setTab] = useState("plot");
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>(
    "/api/analog/measure",
    file
      ? { ...file, signals, ref: ref || null, vdd: vdd > 0 ? vdd : null }
      : null,
  );
  const ok = data && !data.error;
  const main = ok ? data.results[data.selected[0]] : null;
  const shown = ok
    ? [...new Set([...(data.ref ? [data.ref] : []), ...data.selected])]
    : [];

  const fmt = (key: string, unit: string, v: number | null | undefined) =>
    v == null
      ? "–"
      : key === "duty"
        ? `${(v * 100).toFixed(1)}%`
        : key.endsWith("_pct")
          ? `${v.toFixed(2)} %`
          : eng(v, unit);
  const rows = ok
    ? [
        ...data.labels,
        { key: "duty", label: "Duty cycle", unit: "" },
        { key: "overshoot_pct", label: "Overshoot (% of VDD)", unit: "" },
        { key: "undershoot_pct", label: "Undershoot (% of VDD)", unit: "" },
      ]
        .filter((l) =>
          data.selected.some((s) => data.results[s][l.key] != null),
        )
        .map((l) => ({
          measurement: l.label,
          ...Object.fromEntries(
            data.selected.map((s) => [
              s,
              fmt(l.key, l.unit, data.results[s][l.key]),
            ]),
          ),
        }))
    : [];

  return (
    <>
      <PageHeader
        area="Analog"
        title="Waveform Measure"
        icon={ChartLine}
        description={
          <>
            Measure transient waveforms: rise/fall time, propagation delay,
            frequency, duty cycle and overshoot. Accepts CSV with a header or
            ngspice <code className="font-mono text-[13px]">wrdata</code>{" "}
            output.
          </>
        }
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <FileSource
            label="Waveform data"
            examples={["analog/inverter_tran.csv"]}
            accept=".csv,.txt,.dat"
            onChange={setFiles}
          />
          <div className="grid grid-cols-2 gap-3 lg:w-[420px]">
            <Field
              label="Delay reference"
              hint="Propagation delay is measured from this signal's 50% crossings"
            >
              <Select
                value={ref}
                onChange={setRef}
                options={[
                  { value: "", label: "(none)" },
                  ...(ok ? data.signals : [ref]).map((s) => ({
                    value: s,
                    label: s,
                  })),
                ]}
              />
            </Field>
            <Field
              label="VDD (V)"
              hint="Logic levels are 0/VDD. Set 0 to use each signal's min/max."
            >
              <NumberInput value={vdd} onChange={setVdd} min={0} step={0.1} />
            </Field>
          </div>
        </div>
        {ok && (
          <div className="mt-4 border-t border-line pt-4">
            <div className="mb-2 text-[13px] font-medium text-muted">
              Signals to measure
            </div>
            <Chips
              selected={data.selected}
              onChange={(v) => setSignals(v.length ? v : data.selected)}
              options={data.signals.map((s) => ({ value: s, label: s }))}
            />
          </div>
        )}
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!file ? (
        <EmptyState
          icon={ChartLine}
          title="No waveform yet"
          text="Upload a CSV (time column first) or ngspice wrdata output."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : data?.error ? (
        <Alert tone="bad">{data.error}</Alert>
      ) : (
        ok &&
        main && (
          <>
            <KpiGrid
              items={[
                {
                  label: "Avg. delay (tpd)",
                  value: eng(main.tpd, "s"),
                  note: data.ref
                    ? `${data.selected[0]} vs ${data.ref}`
                    : "pick a reference",
                  tone: "info",
                },
                {
                  label: "Rise time",
                  value: eng(main.rise_time, "s"),
                  note: "10–90 %",
                },
                {
                  label: "Fall time",
                  value: eng(main.fall_time, "s"),
                  note: "90–10 %",
                },
                {
                  label: "Frequency",
                  value: eng(main.frequency, "Hz"),
                  note:
                    main.duty != null
                      ? `duty ${(main.duty * 100).toFixed(1)}%`
                      : undefined,
                },
                {
                  label: "Swing",
                  value: `${+((main.vmax ?? 0) - (main.vmin ?? 0)).toPrecision(3)} V`,
                  note: `${+(main.vmin ?? 0).toPrecision(3)} … ${+(main.vmax ?? 0).toPrecision(3)} V`,
                },
              ]}
            />
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { id: "plot", label: "Waveforms", icon: ChartLine },
                {
                  id: "table",
                  label: "All measurements",
                  icon: Table,
                  count: rows.length,
                },
              ]}
            />
            {tab === "plot" && (
              <Card
                title="Transient waveforms"
                subtitle={vdd > 0 ? "Dashed line = 50 % of VDD" : undefined}
              >
                <div className="h-[380px]">
                  <ResponsiveContainer>
                    <LineChart
                      data={data.plot}
                      margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
                    >
                      <CartesianGrid stroke="var(--line)" />
                      <XAxis
                        dataKey="t_ns"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        stroke="var(--faint)"
                        fontSize={12}
                        tickFormatter={(v) => `${+Number(v).toFixed(2)}`}
                        label={{
                          value: "time (ns)",
                          position: "insideBottom",
                          offset: -4,
                          fill: "var(--muted)",
                          fontSize: 12,
                        }}
                      />
                      <YAxis
                        stroke="var(--faint)"
                        fontSize={12}
                        unit=" V"
                        width={56}
                      />
                      <Tooltip
                        labelFormatter={(v) => `${Number(v).toFixed(4)} ns`}
                        formatter={(v) => `${Number(v).toFixed(3)} V`}
                        contentStyle={{
                          background: "var(--surface)",
                          border: "1px solid var(--line)",
                          borderRadius: 8,
                          fontSize: 12.5,
                        }}
                      />
                      <Legend verticalAlign="top" height={30} />
                      {vdd > 0 && (
                        <ReferenceLine
                          y={vdd / 2}
                          stroke="var(--faint)"
                          strokeDasharray="5 5"
                        />
                      )}
                      {shown.map((s, i) => (
                        <Line
                          key={s}
                          dataKey={s}
                          stroke={PALETTE[i % PALETTE.length]}
                          strokeWidth={1.8}
                          dot={false}
                          isAnimationActive={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            )}
            {tab === "table" && (
              <Card bodyClass="p-4" actions={undefined}>
                <DataTable
                  rows={rows}
                  columns={[
                    { key: "measurement", header: "Measurement" },
                    ...data.selected.map((s) => ({
                      key: s,
                      header: s,
                      align: "right" as const,
                      mono: true,
                    })),
                  ]}
                />
                <button
                  className="mt-3 text-[13px] font-medium text-brand hover:underline"
                  onClick={() =>
                    downloadText("measurements.csv", toCSV(rows), "text/csv")
                  }
                >
                  Export CSV
                </button>
              </Card>
            )}
          </>
        )
      )}
    </>
  );
}
