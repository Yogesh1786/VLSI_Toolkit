import { useState } from "react";
import {
  CircuitBoard,
  Code,
  Cpu,
  ListTree,
  Network,
  ShieldCheck,
  SlidersHorizontal,
  Unplug,
} from "lucide-react";
import { useAnalysis, type SourceFile, initialExample } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Segmented,
  Tabs,
} from "../components/ui";

type Mos = {
  name: string;
  scope: string;
  model: string;
  d: string;
  g: string;
  s: string;
  b: string;
  w_text: string;
  l_text: string;
  w_over_l: number | null;
  nf: string;
  m: string;
};
type Result = {
  title: string;
  params: Record<string, string>;
  analyses: string[];
  measures: string[];
  includes: string[];
  devices: {
    name: string;
    type: string;
    scope: string;
    nodes: string[];
    model: string;
    params: Record<string, string>;
  }[];
  subckts: {
    name: string;
    pins: string[];
    devices: number;
    instances: number;
  }[];
  mosfets: Mos[];
  issues: string[];
};

const EXAMPLES = {
  buggy: "analog/buggy_bias.sp",
  chain: "analog/inverter_chain.sp",
} as const;

export default function NetlistCheck() {
  const [example, setExample] = useState<keyof typeof EXAMPLES>(() => initialExample("buggy", EXAMPLES));
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("checks");
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>(
    "/api/analog/netlist",
    file,
  );

  const typeCounts = data
    ? Object.entries(
        data.devices.reduce<Record<string, number>>((acc, d) => {
          const k = `${d.scope}|${d.type}`;
          acc[k] = (acc[k] ?? 0) + 1;
          return acc;
        }, {}),
      ).map(([k, count]) => {
        const [scope, type] = k.split("|");
        return { scope, type, count };
      })
    : [];

  return (
    <>
      <PageHeader
        area="Analog"
        title="Netlist Check"
        icon={CircuitBoard}
        description={
          <>
            Summarize a SPICE netlist and catch connectivity mistakes before
            simulating. The example{" "}
            <code className="font-mono text-[13px]">buggy_bias.sp</code> has a
            floating gate and a node-name typo.
          </>
        }
      />
      <Card className="mb-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className="text-[13px] font-medium text-muted">Example</span>
          <Segmented
            size="sm"
            value={example}
            onChange={setExample}
            options={[
              { value: "buggy", label: "Current mirror (buggy)" },
              { value: "chain", label: "Inverter chain (clean)" },
            ]}
          />
        </div>
        <FileSource
          label="SPICE netlist"
          examples={[EXAMPLES[example]]}
          accept=".sp,.cir,.spice,.net,.ckt"
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
          icon={CircuitBoard}
          title="No netlist yet"
          text="Upload a SPICE netlist (.sp, .cir, .spice)."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : (
        data && (
          <>
            <KpiGrid
              items={[
                {
                  label: "Devices",
                  value: data.devices.length,
                  note:
                    data.title.replace(/^\*\s*/, "").slice(0, 40) || undefined,
                },
                { label: "MOSFETs", value: data.mosfets.length, tone: "info" },
                { label: "Sub-circuits", value: data.subckts.length },
                {
                  label: "Analyses",
                  value: data.analyses.length,
                  note:
                    data.analyses.map((a) => a.split(" ")[0]).join(", ") ||
                    "none",
                  tone: data.analyses.length ? "neutral" : "warn",
                },
                {
                  label: "Connectivity",
                  value: data.issues.length
                    ? `${data.issues.length} issue${data.issues.length > 1 ? "s" : ""}`
                    : "OK",
                  note: data.issues.length ? "see Checks" : "no floating nodes",
                  tone: data.issues.length ? "bad" : "good",
                },
              ]}
            />
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                {
                  id: "checks",
                  label: "Checks",
                  icon: ShieldCheck,
                  count: data.issues.length,
                },
                {
                  id: "mos",
                  label: "MOSFETs",
                  icon: Cpu,
                  count: data.mosfets.length,
                },
                {
                  id: "dev",
                  label: "Devices",
                  icon: ListTree,
                  count: data.devices.length,
                },
                {
                  id: "sub",
                  label: "Sub-circuits",
                  icon: Network,
                  count: data.subckts.length,
                },
                {
                  id: "par",
                  label: "Parameters & analyses",
                  icon: SlidersHorizontal,
                },
                { id: "src", label: "Source", icon: Code },
              ]}
            />
            {tab === "checks" &&
              (data.issues.length === 0 ? (
                <Alert tone="good" title="No connectivity issues found" />
              ) : (
                <>
                  {data.issues.map((i) => (
                    <Alert key={i} tone="bad">
                      <Unplug className="mr-1.5 inline size-3.5" />
                      {i}
                    </Alert>
                  ))}
                  <p className="mt-2 text-[13.5px] text-muted">
                    A node touching only one terminal, or only MOSFET gates, has
                    nothing defining its voltage: a classic cause of convergence
                    failures or a wrong operating point.
                  </p>
                </>
              ))}
            {tab === "mos" && (
              <Card bodyClass="p-4">
                {data.mosfets.length ? (
                  <DataTable
                    rows={data.mosfets}
                    columns={[
                      { key: "name", header: "Name", mono: true },
                      { key: "scope", header: "Scope" },
                      {
                        key: "model",
                        header: "Model",
                        render: (m) => <Badge tone="info">{m.model}</Badge>,
                      },
                      { key: "d", header: "D", mono: true },
                      { key: "g", header: "G", mono: true },
                      { key: "s", header: "S", mono: true },
                      { key: "b", header: "B", mono: true },
                      { key: "w_text", header: "W", align: "right" },
                      { key: "l_text", header: "L", align: "right" },
                      {
                        key: "w_over_l",
                        header: "W/L",
                        align: "right",
                        render: (m) =>
                          m.w_over_l ? m.w_over_l.toFixed(2) : "–",
                      },
                      { key: "nf", header: "nf", align: "right" },
                      { key: "m", header: "m", align: "right" },
                    ]}
                  />
                ) : (
                  <p className="text-muted">No MOSFETs in this netlist.</p>
                )}
              </Card>
            )}
            {tab === "dev" && (
              <div className="grid gap-5 xl:grid-cols-[1fr_2fr]">
                <Card title="By type" bodyClass="p-4">
                  <DataTable
                    rows={typeCounts}
                    columns={[
                      { key: "scope", header: "Scope" },
                      { key: "type", header: "Type" },
                      { key: "count", header: "Count", align: "right" },
                    ]}
                  />
                </Card>
                <Card title="All devices" bodyClass="p-4">
                  <DataTable
                    rows={data.devices}
                    searchable
                    columns={[
                      { key: "name", header: "Name", mono: true },
                      { key: "type", header: "Type" },
                      { key: "scope", header: "Scope" },
                      {
                        key: "nodes",
                        header: "Nodes",
                        mono: true,
                        value: (d) => d.nodes.join(" "),
                      },
                      { key: "model", header: "Model / value", mono: true },
                      {
                        key: "params",
                        header: "Parameters",
                        mono: true,
                        value: (d) =>
                          Object.entries(d.params)
                            .map(([k, v]) => `${k}=${v}`)
                            .join(" "),
                      },
                    ]}
                  />
                </Card>
              </div>
            )}
            {tab === "sub" && (
              <Card bodyClass="p-4">
                {data.subckts.length ? (
                  <DataTable
                    rows={data.subckts}
                    columns={[
                      { key: "name", header: "Name", mono: true },
                      {
                        key: "pins",
                        header: "Pins",
                        mono: true,
                        value: (s) => s.pins.join(" "),
                      },
                      {
                        key: "devices",
                        header: "Devices inside",
                        align: "right",
                      },
                      { key: "instances", header: "Instances", align: "right" },
                    ]}
                  />
                ) : (
                  <p className="text-muted">No sub-circuits.</p>
                )}
              </Card>
            )}
            {tab === "par" && (
              <div className="grid gap-5 lg:grid-cols-2">
                <Card title=".param values" bodyClass="p-4">
                  {Object.keys(data.params).length ? (
                    <DataTable
                      rows={Object.entries(data.params).map(
                        ([name, value]) => ({ name, value }),
                      )}
                      columns={[
                        { key: "name", header: "Parameter", mono: true },
                        { key: "value", header: "Value", align: "right" },
                      ]}
                    />
                  ) : (
                    <p className="text-muted">No .param statements.</p>
                  )}
                </Card>
                <Card title="Analyses & measurements">
                  <CodeBlock
                    code={
                      [
                        ...data.analyses,
                        ...data.measures.map((m) => `.meas ${m}`),
                      ].join("\n") || "(none)"
                    }
                    download={false}
                  />
                </Card>
              </div>
            )}
            {tab === "src" && (
              <CodeBlock code={file.text} filename={file.name} />
            )}
          </>
        )
      )}
    </>
  );
}
