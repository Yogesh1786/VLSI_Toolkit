import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Code,
  Download,
  FlaskConical,
  PlayCircle,
} from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { CodeBlock } from "../components/CodeBlock";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  KpiGrid,
  LoadingBlock,
  NumberInput,
  PageHeader,
  Select,
  Tabs,
} from "../components/ui";
import { downloadAll } from "../lib/format";

type Result = {
  error?: string;
  modules: string[];
  module: string;
  clocks: string[];
  resets: { name: string; active_low: boolean }[];
  data_inputs: string[];
  files: Record<string, string>;
};

export default function Testbench() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [module, setModule] = useState("");
  const [cycles, setCycles] = useState(100);
  const [period, setPeriod] = useState(10);
  const [tab, setTab] = useState("v");
  const file = files?.[0] ?? null;
  const { data, loading, error } = useAnalysis<Result>(
    "/api/verif/testbench",
    file
      ? {
          ...file,
          module: module || null,
          cycles: Math.max(1, cycles),
          period: Math.max(1, period),
        }
      : null,
  );
  const ok = data && !data.error;
  const tbName = ok ? `tb_${data.module}.v` : "",
    pyName = ok ? `test_${data.module}.py` : "";

  return (
    <>
      <PageHeader
        area="Verification"
        title="Testbench Generator"
        icon={FlaskConical}
        description="Generate a ready-to-run testbench: clock and reset are found from the port names, inputs get random stimulus, and waveforms are dumped to a VCD file."
        actions={
          ok ? (
            <Button
              variant="primary"
              icon={Download}
              onClick={() => downloadAll(data.files)}
            >
              Download both
            </Button>
          ) : undefined
        }
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <FileSource
            label="Design (RTL)"
            examples={["counter.v"]}
            accept=".v,.sv"
            onChange={(f) => {
              setFiles(f);
              setModule("");
            }}
          />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:w-[480px]">
            {ok && data.modules.length > 1 && (
              <Field label="Top module">
                <Select
                  value={data.module}
                  onChange={setModule}
                  options={data.modules.map((m) => ({ value: m, label: m }))}
                />
              </Field>
            )}
            <Field label="Stimulus cycles">
              <NumberInput value={cycles} onChange={setCycles} min={1} />
            </Field>
            <Field label="Clock period (ns)">
              <NumberInput value={period} onChange={setPeriod} min={1} />
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
          icon={FlaskConical}
          title="No design yet"
          text="Upload an RTL file to generate its testbench."
        />
      ) : loading && !data ? (
        <LoadingBlock label="Generating…" />
      ) : data?.error ? (
        <Alert tone="bad">{data.error}</Alert>
      ) : (
        ok && (
          <>
            <KpiGrid
              items={[
                { label: "Top module", value: data.module },
                {
                  label: "Clock",
                  value: data.clocks.join(", ") || "none",
                  note: data.clocks.length
                    ? `${+(1000 / period).toFixed(3)} MHz`
                    : "delay-based stimulus",
                  tone: "info",
                },
                {
                  label: "Reset",
                  value: data.resets.map((r) => r.name).join(", ") || "none",
                  note:
                    data.resets
                      .map((r) => (r.active_low ? "active-low" : "active-high"))
                      .join(", ") || undefined,
                },
                {
                  label: "Randomized inputs",
                  value: data.data_inputs.length,
                  note: data.data_inputs.slice(0, 3).join(", ") || undefined,
                },
                { label: "Files", value: 2, note: "Verilog + cocotb" },
              ]}
            />
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { id: "v", label: "Verilog testbench", icon: Code },
                { id: "py", label: "cocotb (Python) test", icon: Code },
                { id: "run", label: "How to run", icon: PlayCircle },
              ]}
            />
            {tab === "v" && (
              <CodeBlock
                code={data.files[tbName]}
                lang="verilog"
                filename={tbName}
              />
            )}
            {tab === "py" && (
              <CodeBlock
                code={data.files[pyName]}
                lang="python"
                filename={pyName}
              />
            )}
            {tab === "run" && (
              <div className="grid gap-5 lg:grid-cols-2">
                <Card
                  title="Icarus Verilog + GTKWave"
                  subtitle="free, open-source simulator"
                >
                  <CodeBlock
                    code={`iverilog -g2012 -o sim.out ${tbName} ${file.name}\nvvp sim.out\ngtkwave tb_${data.module}.vcd`}
                    lang="bash"
                    download={false}
                  />
                </Card>
                <Card
                  title="cocotb"
                  subtitle="pip install cocotb (+ a simulator)"
                >
                  <CodeBlock
                    code={`python ${pyName}`}
                    lang="bash"
                    download={false}
                  />
                  <Link
                    to="/vcd"
                    className="mt-4 inline-flex items-center gap-1.5 text-[14px] font-medium text-brand hover:underline"
                  >
                    Then open the waveform in the Waveform Viewer{" "}
                    <ArrowRight className="size-4" />
                  </Link>
                </Card>
              </div>
            )}
          </>
        )
      )}
    </>
  );
}
