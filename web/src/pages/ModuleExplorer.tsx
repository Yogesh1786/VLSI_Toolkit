import { useState } from "react";
import { Code, Copy, Cpu, FileX, ListTree } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  Field,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Select,
  Tabs,
  TextInput,
} from "../components/ui";

type Port = {
  name: string;
  direction: string;
  net_type: string;
  signed: boolean;
  range: string;
  width: number | null;
};
type Param = {
  name: string;
  default: string;
  value: number | null;
  local: boolean;
};
type Mod = {
  name: string;
  ansi: boolean;
  warnings: string[];
  parameters: Param[];
  ports: Port[];
  instantiation: string;
};

const dirTone = (d: string) =>
  (d === "input" ? "info" : d === "output" ? "good" : "warn") as
    | "info"
    | "good"
    | "warn";

export default function ModuleExplorer() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [modName, setModName] = useState("");
  const [inst, setInst] = useState("");
  const [tab, setTab] = useState("ports");
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<{ modules: Mod[] }>(
    "/api/rtl/parse",
    file,
  );
  const modules = data?.modules ?? [];
  const mod =
    modules.find((m) => m.name === modName) ?? modules[modules.length - 1];

  const instText = mod
    ? inst.trim()
      ? mod.instantiation.replace(`u_${mod.name}`, inst.trim())
      : mod.instantiation
    : "";

  return (
    <>
      <PageHeader
        area="RTL design"
        title="Module Explorer"
        icon={Cpu}
        description="Read a Verilog/SystemVerilog file and see its modules, parameters and ports, with widths calculated from the parameters."
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
          <FileSource
            label="Verilog source"
            examples={["fifo.v"]}
            accept=".v,.sv,.vh,.svh"
            onChange={setFiles}
          />
          {modules.length > 1 && (
            <Field
              label="Module"
              hint="The file has several modules; the last one is usually the top"
            >
              <Select
                value={mod?.name ?? ""}
                onChange={setModName}
                options={modules.map((m) => ({ value: m.name, label: m.name }))}
              />
            </Field>
          )}
        </div>
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!file ? (
        <EmptyState
          icon={Cpu}
          title="No file yet"
          text="Upload a Verilog or SystemVerilog file to begin."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : !mod ? (
        <EmptyState
          icon={FileX}
          title="No module found"
          text="The file does not contain a `module ... endmodule` block."
        />
      ) : (
        <>
          <KpiGrid
            items={[
              {
                label: "Module",
                value: mod.name,
                note:
                  modules.length > 1 ? `${modules.length} in file` : undefined,
              },
              {
                label: "Port style",
                value: mod.ansi ? "ANSI" : "Non-ANSI",
                note: mod.ansi ? "Verilog-2001" : "Verilog-1995",
              },
              {
                label: "Parameters",
                value: mod.parameters.length,
                note: mod.parameters.some((p) => p.local)
                  ? `${mod.parameters.filter((p) => p.local).length} local`
                  : undefined,
              },
              {
                label: "Inputs",
                value: mod.ports.filter((p) => p.direction === "input").length,
                tone: "info",
                note: `${mod.ports.filter((p) => p.direction === "input").reduce((s, p) => s + (p.width ?? 0), 0)} bits`,
              },
              {
                label: "Outputs",
                value: mod.ports.filter((p) => p.direction === "output").length,
                tone: "good",
                note: `${mod.ports.filter((p) => p.direction === "output").reduce((s, p) => s + (p.width ?? 0), 0)} bits`,
              },
            ]}
          />
          {mod.warnings.map((w) => (
            <Alert key={w} tone="warn">
              {w}
            </Alert>
          ))}
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              {
                id: "ports",
                label: "Ports & parameters",
                icon: ListTree,
                count: mod.ports.length,
              },
              { id: "inst", label: "Instantiation", icon: Copy },
              { id: "src", label: "Source", icon: Code },
            ]}
          />
          {tab === "ports" && (
            <div className="grid gap-5 xl:grid-cols-[3fr_2fr]">
              <Card
                title="Ports"
                subtitle={`${mod.ports.length} total`}
                bodyClass="p-0"
              >
                <div className="p-4">
                  <DataTable
                    rows={mod.ports}
                    searchable
                    columns={[
                      { key: "name", header: "Port", mono: true },
                      {
                        key: "direction",
                        header: "Direction",
                        render: (p) => (
                          <Badge tone={dirTone(p.direction)}>
                            {p.direction}
                          </Badge>
                        ),
                      },
                      { key: "net_type", header: "Type" },
                      {
                        key: "signed",
                        header: "Sign",
                        render: (p) => (p.signed ? "signed" : ""),
                      },
                      {
                        key: "range",
                        header: "Range",
                        mono: true,
                        render: (p) => p.range || "–",
                      },
                      {
                        key: "width",
                        header: "Width",
                        align: "right",
                        render: (p) =>
                          p.width == null ? "?" : `${p.width} bit`,
                      },
                    ]}
                  />
                </div>
              </Card>
              <Card
                title="Parameters"
                subtitle="values evaluated from the defaults"
                bodyClass="p-0"
              >
                <div className="p-4">
                  {mod.parameters.length ? (
                    <DataTable
                      rows={mod.parameters}
                      columns={[
                        { key: "name", header: "Name", mono: true },
                        { key: "default", header: "Default", mono: true },
                        { key: "value", header: "Value", align: "right" },
                        {
                          key: "local",
                          header: "Kind",
                          render: (p) => (
                            <Badge tone={p.local ? "neutral" : "info"}>
                              {p.local ? "localparam" : "parameter"}
                            </Badge>
                          ),
                        },
                      ]}
                    />
                  ) : (
                    <p className="text-[14px] text-muted">
                      This module has no parameters.
                    </p>
                  )}
                </div>
              </Card>
            </div>
          )}
          {tab === "inst" && (
            <div className="space-y-4">
              <div className="max-w-sm">
                <Field label="Instance name">
                  <TextInput
                    mono
                    value={inst}
                    onChange={setInst}
                    placeholder={`u_${mod.name}`}
                  />
                </Field>
              </div>
              <CodeBlock
                code={instText}
                lang="verilog"
                filename={`${mod.name}_inst.v`}
              />
            </div>
          )}
          {tab === "src" && file && (
            <CodeBlock code={file.text} lang="verilog" filename={file.name} />
          )}
        </>
      )}
    </>
  );
}
