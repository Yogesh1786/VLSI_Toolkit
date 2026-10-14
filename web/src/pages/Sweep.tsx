import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Download,
  FileText,
  Play,
  PlayCircle,
  SlidersHorizontal,
} from "lucide-react";
import { postJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { CodeBlock } from "../components/CodeBlock";
import { DataTable } from "../components/DataTable";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Select,
  Spinner,
  Tabs,
  TextInput,
} from "../components/ui";
import { downloadAll, downloadText, eng, PALETTE, toCSV } from "../lib/format";

type Result = {
  error?: string;
  params: Record<string, string>;
  current: string | null;
  values: string[];
  measures: string[];
  ngspice: boolean;
  netlists: { name: string; value: string; text: string }[];
};
type RunResult = {
  measures: string[];
  rows: Record<string, number | string | null>[];
};

export default function Sweep() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [param, setParam] = useState("vdd");
  const [values, setValues] = useState("1.2:1.8:0.2");
  const [tab, setTab] = useState("prev");
  const [preview, setPreview] = useState("");
  const [run, setRun] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>(
    "/api/analog/sweep",
    file && param && values ? { ...file, param, values } : null,
    400,
  );
  const ok = data && !data.error;
  useEffect(() => {
    setRun(null);
  }, [file, param, values]);
  const shown = ok
    ? (data.netlists.find((n) => n.name === preview) ?? data.netlists[0])
    : null;

  const simulate = async () => {
    if (!file) return;
    setRunning(true);
    setRunError(null);
    try {
      setRun(
        await postJSON<RunResult>("/api/analog/sweep/run", {
          ...file,
          param,
          values,
        }),
      );
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <PageHeader
        area="Analog"
        title="Parameter Sweep"
        icon={SlidersHorizontal}
        description={
          <>
            Make one netlist per value of a{" "}
            <code className="font-mono text-[13px]">.param</code> (supply,
            sizing, load…). With ngspice installed, run them all here and
            compare the <code className="font-mono text-[13px]">.meas</code>{" "}
            results.
          </>
        }
        actions={
          ok ? (
            <Button
              variant="primary"
              icon={Download}
              onClick={() =>
                downloadAll(
                  Object.fromEntries(
                    data.netlists.map((n) => [n.name, n.text]),
                  ),
                )
              }
            >
              Download netlists
            </Button>
          ) : undefined
        }
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <FileSource
            label="SPICE netlist"
            examples={["analog/inverter_chain.sp"]}
            accept=".sp,.cir,.spice,.net"
            onChange={setFiles}
          />
          <div className="grid grid-cols-2 gap-3 lg:w-[440px]">
            <Field label="Parameter">
              {ok && Object.keys(data.params).length ? (
                <Select
                  value={param}
                  onChange={(v) => {
                    setParam(v);
                    const cur = data.params[v];
                    if (v !== "vdd" && cur) setValues(cur.replace(/\s+/g, ""));
                  }}
                  options={Object.keys(data.params).map((p) => ({
                    value: p,
                    label: p.toUpperCase(),
                  }))}
                />
              ) : (
                <TextInput value={param} onChange={setParam} mono />
              )}
            </Field>
            <Field
              label="Values"
              hint="start:stop:step (inclusive) or a comma list. SPICE suffixes work: 0.3u,0.42u"
            >
              <TextInput
                value={values}
                onChange={setValues}
                mono
                placeholder="1.2:1.8:0.2"
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
          icon={SlidersHorizontal}
          title="No netlist yet"
          text="Upload a SPICE netlist that defines .param values."
        />
      ) : loading && !data ? (
        <LoadingBlock label="Generating…" />
      ) : data?.error ? (
        <Alert tone="bad">{data.error}</Alert>
      ) : (
        ok &&
        shown && (
          <>
            <KpiGrid
              items={[
                {
                  label: "Parameter",
                  value: param.toUpperCase(),
                  note: data.current
                    ? `now ${data.current}`
                    : "added to netlist",
                },
                {
                  label: "Sweep points",
                  value: data.values.length,
                  note: `${data.values[0]} … ${data.values[data.values.length - 1]}`,
                },
                {
                  label: "Measurements",
                  value: data.measures.length,
                  note:
                    data.measures.slice(0, 3).join(", ") || "none in netlist",
                  tone: data.measures.length ? "neutral" : "warn",
                },
                {
                  label: "ngspice",
                  value: data.ngspice ? "Found" : "Not installed",
                  tone: data.ngspice ? "good" : "warn",
                  note: data.ngspice ? "can simulate here" : "generate only",
                },
                {
                  label: "Netlists",
                  value: data.netlists.length,
                  note: "ready to download",
                },
              ]}
            />
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                {
                  id: "prev",
                  label: "Netlist preview",
                  icon: FileText,
                  count: data.netlists.length,
                },
                { id: "sim", label: "Simulate", icon: PlayCircle },
              ]}
            />
            {tab === "prev" && (
              <div className="space-y-4">
                <div className="w-full max-w-sm">
                  <Select
                    value={shown.name}
                    onChange={setPreview}
                    options={data.netlists.map((n) => ({
                      value: n.name,
                      label: `${param.toUpperCase()} = ${n.value}  ·  ${n.name}`,
                    }))}
                  />
                </div>
                <CodeBlock
                  code={shown.text}
                  filename={shown.name}
                  maxHeight={480}
                />
              </div>
            )}
            {tab === "sim" &&
              (!data.ngspice ? (
                <Alert tone="info" title="ngspice is not installed">
                  Install it from ngspice.sourceforge.io and add its{" "}
                  <code>bin</code> folder to PATH, then restart the API server
                  to simulate the sweep here. You can still download the
                  netlists and run them yourself.
                </Alert>
              ) : (
                <Card
                  title="Simulation"
                  subtitle={
                    data.measures.length
                      ? `Collects: ${data.measures.join(", ")}`
                      : "The netlist has no .meas statements"
                  }
                  actions={
                    <Button
                      variant="primary"
                      icon={running ? undefined : Play}
                      onClick={simulate}
                      disabled={running}
                    >
                      {running ? (
                        <>
                          <Spinner className="text-white" /> Running…
                        </>
                      ) : (
                        "Run ngspice"
                      )}
                    </Button>
                  }
                >
                  {runError && <Alert tone="bad">{runError}</Alert>}
                  {!run && !running && (
                    <p className="text-muted">
                      Press “Run ngspice” to simulate all {data.netlists.length}{" "}
                      netlists.
                    </p>
                  )}
                  {run && (
                    <div className="space-y-5">
                      <div className="h-80">
                        <ResponsiveContainer>
                          <LineChart
                            data={run.rows}
                            margin={{
                              top: 10,
                              right: 20,
                              left: 10,
                              bottom: 10,
                            }}
                          >
                            <CartesianGrid stroke="var(--line)" />
                            <XAxis
                              dataKey="value_num"
                              type="number"
                              domain={["dataMin", "dataMax"]}
                              stroke="var(--faint)"
                              fontSize={12}
                            />
                            <YAxis
                              stroke="var(--faint)"
                              fontSize={12}
                              tickFormatter={(v) => eng(v)}
                              width={70}
                            />
                            <Tooltip
                              formatter={(v) => eng(Number(v))}
                              contentStyle={{
                                background: "var(--surface)",
                                border: "1px solid var(--line)",
                                borderRadius: 8,
                              }}
                            />
                            <Legend />
                            {run.measures.map((m, i) => (
                              <Line
                                key={m}
                                dataKey={m}
                                stroke={PALETTE[i % PALETTE.length]}
                                strokeWidth={2}
                                dot
                              />
                            ))}
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                      <DataTable
                        rows={run.rows}
                        columns={[
                          { key: "value", header: param.toUpperCase() },
                          ...run.measures.map((m) => ({
                            key: m,
                            header: m,
                            align: "right" as const,
                            render: (
                              r: Record<string, number | string | null>,
                            ) => eng(r[m] as number | null),
                          })),
                        ]}
                      />
                      <Button
                        icon={Download}
                        onClick={() =>
                          downloadText(
                            `sweep_${param}.csv`,
                            toCSV(run.rows),
                            "text/csv",
                          )
                        }
                      >
                        Results CSV
                      </Button>
                    </div>
                  )}
                </Card>
              ))}
          </>
        )
      )}
    </>
  );
}
