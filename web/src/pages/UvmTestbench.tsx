import { useState } from "react";
import { Archive, Boxes, FileCode, Workflow } from "lucide-react";
import { request, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { CodeBlock } from "../components/CodeBlock";
import { Alert, Button, Card, EmptyState, Field, KpiGrid, LoadingBlock, NumberInput, PageHeader, Select, TextInput } from "../components/ui";
import { cx } from "../lib/format";

type Result = {
  files: Record<string, string>; top: string; prefix: string; notes: string[]; modules: string[];
  clock: string | null; resets: string[]; inputs: string[]; outputs: string[];
};

/** What each generated file is for, in reading order. */
const ROLE: [RegExp, string][] = [
  [/_if\.sv$/, "Interface with driver and monitor clocking blocks"],
  [/_seq_item\.sv$/, "Transaction: random inputs, observed outputs"],
  [/_sequence\.sv$/, "Random stimulus sequence"],
  [/_driver\.sv$/, "Drives one item per clock"],
  [/_monitor\.sv$/, "Samples the interface every clock"],
  [/_agent\.sv$/, "Sequencer + driver + monitor"],
  [/_scoreboard\.sv$/, "Compares outputs with your reference model"],
  [/_coverage\.sv$/, "Functional coverage of the inputs"],
  [/_env\.sv$/, "Connects agent, scoreboard and coverage"],
  [/_base_test\.sv$/, "Starts the sequence"],
  [/_pkg\.sv$/, "Package: includes the classes in compile order"],
  [/^tb_top\.sv$/, "Clock, reset, DUT and run_test()"],
  [/^files\.f$/, "File list with Questa / VCS / Xcelium commands"],
];
const role = (name: string) => ROLE.find(([re]) => re.test(name))?.[1] ?? "";
const order = (name: string) => {
  const i = ROLE.findIndex(([re]) => re.test(name));
  return i < 0 ? 99 : i;
};

export default function UvmTestbench() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [module, setModule] = useState("");
  const [prefix, setPrefix] = useState("");
  const [items, setItems] = useState(20);
  const [selected, setSelected] = useState("");
  const [zipError, setZipError] = useState<string | null>(null);
  const file = files?.[0] ?? null;
  const body = file ? { ...file, module: module || null, prefix: prefix.trim() || null, num_items: Math.max(1, items) } : null;
  const { data, loading, error } = useAnalysis<Result>("/api/verif/uvm", body, 400);
  const names = data ? Object.keys(data.files).sort((a, b) => order(a) - order(b)) : [];
  const shown = data && (names.includes(selected) ? selected : names[0]);

  const downloadZip = async () => {
    if (!body) return;
    setZipError(null);
    try {
      const r = await request("/api/verif/uvm/zip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `${data?.prefix ?? "uvm"}_uvm.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setZipError((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader area="Verification" title="UVM Testbench" icon={Workflow}
        description="Generate a complete UVM environment for a module: interface with clocking blocks, sequence item, sequence, driver, monitor, agent, scoreboard, functional coverage, environment, base test and tb_top. Only the reference model is left for you."
        actions={data ? <Button variant="primary" icon={Archive} onClick={downloadZip}>Download all (.zip)</Button> : undefined} />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <FileSource label="Design under test" examples={["fifo.v", "counter.v", "alu.v", "rtl_project/uart_tx.v"]} accept=".v,.sv" wsKinds={["rtl"]} onChange={setFiles} />
          <div className="grid grid-cols-2 gap-3 lg:w-80">
            {data && data.modules.length > 1 && (
              <Field label="Module" className="col-span-2">
                <Select value={module || data.top} onChange={setModule} options={data.modules.map((m) => ({ value: m, label: m }))} />
              </Field>
            )}
            <Field label="Class prefix" hint="Defaults to the module name.">
              <TextInput value={prefix} onChange={setPrefix} placeholder={data?.top ?? "module"} mono />
            </Field>
            <Field label="Items per test">
              <NumberInput value={items} onChange={setItems} min={1} max={10000} />
            </Field>
          </div>
        </div>
      </Card>

      {(error || zipError) && <Alert tone="bad" title="Could not generate">{error ?? zipError}</Alert>}
      {!file ? <EmptyState icon={Workflow} title="No design yet" text="Upload a Verilog/SystemVerilog module or pick an example." />
        : loading && !data ? <LoadingBlock label="Generating…" />
        : data && (
          <>
            <KpiGrid items={[
              { label: "Files", value: names.length, note: `prefix ${data.prefix}_*`, tone: "info" },
              { label: "Clock", value: data.clock ?? "none", note: data.clock ? "drives the clocking blocks" : "generated in tb_top" },
              { label: "Reset", value: data.resets[0] ?? "none", note: data.resets.length ? "held for 5 cycles" : "no reset port" },
              { label: "Random inputs", value: data.inputs.length, note: data.inputs.slice(0, 4).join(", ") || "–" },
              { label: "Observed outputs", value: data.outputs.length, note: data.outputs.slice(0, 4).join(", ") || "–" },
            ]} />
            {data.notes.map((n) => <Alert key={n} tone="warn">{n}</Alert>)}
            <Alert tone="info" title="Next steps">
              Add your constraints in <code className="font-mono">{data.prefix}_seq_item.sv</code> and the expected behaviour in{" "}
              <code className="font-mono">predict()</code> of <code className="font-mono">{data.prefix}_scoreboard.sv</code>, then compile with the
              commands in <code className="font-mono">files.f</code>. The register model for a register block is on the Register Map page (UVM RAL tab).
            </Alert>
            <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
              <Card bodyClass="p-2" title={<span className="flex items-center gap-2"><Boxes className="size-4 text-brand" /> Generated files</span>}>
                {names.map((n) => (
                  <button key={n} onClick={() => setSelected(n)}
                    className={cx("flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left", shown === n ? "bg-brand-soft" : "hover:bg-surface-2")}>
                    <FileCode className={cx("mt-0.5 size-4 shrink-0", shown === n ? "text-brand" : "text-faint")} />
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-[12.5px] font-medium">{n}</span>
                      <span className="block text-[11.5px] text-muted">{role(n)}</span>
                    </span>
                  </button>
                ))}
              </Card>
              {shown && <CodeBlock code={data.files[shown]} lang="verilog" filename={shown} maxHeight={640} />}
            </div>
          </>
        )}
    </>
  );
}
