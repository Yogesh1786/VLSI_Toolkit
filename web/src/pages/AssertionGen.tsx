import { useEffect, useMemo, useState } from "react";
import { BadgeCheck, Code, ListChecks, ShieldCheck } from "lucide-react";
import { getJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import {
  Alert,
  Badge,
  Card,
  Chips,
  EmptyState,
  Field,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Select,
  Tabs,
  Toggle,
} from "../components/ui";

type Assertion = {
  kind: string;
  name: string;
  type: "assert" | "cover";
  description: string;
  code: string;
};
type Result = {
  error?: string;
  module: string;
  modules?: string[];
  clock: string;
  reset: string | null;
  reset_active_low: boolean;
  fsms: number;
  axi_prefixes: string[];
  assertions: Assertion[];
  counts: Record<string, number>;
  code: string;
  filename: string;
  all_modules?: { file: string; module: string }[];
};

const KIND_TONE: Record<string, "info" | "good" | "warn" | "neutral"> = {
  AXI: "info",
  FSM: "good",
  "One-hot": "warn",
  Outputs: "neutral",
};

export default function AssertionGen() {
  const [examples, setExamples] = useState<string[]>([]);
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [module, setModule] = useState("uart_axil");
  const [opts, setOpts] = useState({
    axi: true,
    fsm: true,
    onehot: true,
    outputs: true,
    covers: true,
  });
  const [tab, setTab] = useState("code");
  const [kinds, setKinds] = useState<string[]>([
    "AXI",
    "FSM",
    "One-hot",
    "Outputs",
  ]);
  useEffect(() => {
    getJSON<string[]>("/api/examples?folder=rtl_project")
      .then((r) => setExamples([...r, "axi/uart_axil.v"]))
      .catch(() => setExamples([]));
  }, []);
  const { data, loading, error } = useAnalysis<Result>(
    "/api/verif/sva",
    files ? { files, module, ...opts } : null,
  );
  const ok = data && !data.error;
  const moduleOptions = useMemo(() => {
    const list =
      data?.all_modules ??
      (data?.modules ?? []).map((m) => ({ file: "", module: m }));
    return list.map((m) => ({
      value: m.module,
      label: m.file ? `${m.module}  ·  ${m.file}` : m.module,
    }));
  }, [data]);
  const asserts = ok
    ? data.assertions.filter((a) => a.type === "assert").length
    : 0;

  return (
    <>
      <PageHeader
        area="Verification"
        title="Assertion Generator"
        icon={ShieldCheck}
        description="Generate SystemVerilog assertions (SVA) and cover points from the RTL: AXI handshake rules, legal FSM states and transitions, one-hot signals and X-free outputs. Paste one include line into the module and every simulation checks them."
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          {examples.length > 0 && (
            <FileSource
              label="RTL files"
              multiple
              examples={examples}
              accept=".v,.sv"
              onChange={setFiles}
            />
          )}
          <div className="space-y-3">
            <Field label="Module">
              <Select
                value={ok ? data.module : module}
                onChange={setModule}
                options={
                  moduleOptions.length
                    ? moduleOptions
                    : [{ value: module, label: module }]
                }
              />
            </Field>
            <div className="grid grid-cols-2 gap-2 pt-1">
              {(
                [
                  ["axi", "AXI rules"],
                  ["fsm", "FSM checks"],
                  ["onehot", "One-hot"],
                  ["outputs", "Outputs known"],
                  ["covers", "Cover points"],
                ] as const
              ).map(([k, l]) => (
                <Toggle
                  key={k}
                  checked={opts[k]}
                  onChange={(v) => setOpts((o) => ({ ...o, [k]: v }))}
                  label={l}
                />
              ))}
            </div>
          </div>
        </div>
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!files ? (
        <EmptyState
          icon={ShieldCheck}
          title="No RTL yet"
          text="Load the RTL files of your design and pick a module."
        />
      ) : loading && !data ? (
        <LoadingBlock label="Generating assertions…" />
      ) : data?.error ? (
        <Alert
          tone="warn"
          title={`Cannot generate assertions for ${data.module ?? "this module"}`}
        >
          {data.error}
        </Alert>
      ) : (
        ok && (
          <>
            <KpiGrid
              items={[
                {
                  label: "Module",
                  value: data.module,
                  note: `clock ${data.clock}`,
                },
                {
                  label: "Assertions",
                  value: asserts,
                  tone: "good",
                  note: "checked every cycle",
                },
                {
                  label: "Cover points",
                  value: data.assertions.length - asserts,
                  tone: "info",
                  note: "prove scenarios happen",
                },
                {
                  label: "AXI interfaces",
                  value: data.axi_prefixes.length,
                  note:
                    data.axi_prefixes.map((p) => `${p}*`).join(", ") || "none",
                },
                {
                  label: "State machines",
                  value: data.fsms,
                  note: data.reset
                    ? `reset ${data.reset} (active-${data.reset_active_low ? "low" : "high"})`
                    : "no reset found",
                },
              ]}
            />
            <Alert tone="info" title="How to use">
              Save the file next to your RTL and add these lines just before{" "}
              <code className="font-mono">endmodule</code>, then simulate with
              <code className="font-mono"> +define+ASSERT_ON</code> (the include
              sees every internal signal and state name):
              <pre className="mt-2 rounded-md bg-surface px-3 py-2 font-mono text-[12.5px] text-fg">
                {'`ifdef ASSERT_ON\n  `include "' + data.filename + '"\n`endif'}
              </pre>
            </Alert>
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { id: "code", label: data.filename, icon: Code },
                {
                  id: "list",
                  label: "Property list",
                  icon: ListChecks,
                  count: data.assertions.length,
                },
              ]}
            />
            {tab === "code" && (
              <CodeBlock
                code={data.code}
                lang="verilog"
                filename={data.filename}
                maxHeight={620}
              />
            )}
            {tab === "list" && (
              <Card bodyClass="p-4">
                <div className="mb-4">
                  <Chips
                    selected={kinds}
                    onChange={setKinds}
                    options={Object.entries(data.counts).map(([k, n]) => ({
                      value: k,
                      label: k,
                      count: n,
                    }))}
                  />
                </div>
                <DataTable
                  rows={data.assertions.filter((a) => kinds.includes(a.kind))}
                  searchable
                  columns={[
                    {
                      key: "kind",
                      header: "Group",
                      render: (a) => (
                        <Badge tone={KIND_TONE[a.kind] ?? "neutral"}>
                          {a.kind}
                        </Badge>
                      ),
                    },
                    {
                      key: "type",
                      header: "Type",
                      render: (a) =>
                        a.type === "assert" ? (
                          <span className="inline-flex items-center gap-1 text-good">
                            <BadgeCheck className="size-3.5" />
                            assert
                          </span>
                        ) : (
                          <span className="text-info">cover</span>
                        ),
                    },
                    { key: "name", header: "Name", mono: true },
                    {
                      key: "description",
                      header: "Checks / covers",
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
