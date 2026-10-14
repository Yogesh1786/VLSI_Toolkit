import { useEffect, useState } from "react";
import { ArrowLeftRight, Download, FileText, FlaskConical, Pencil, Rows3, Table2, Terminal, Cpu } from "lucide-react";
import { useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { CodeBlock } from "../components/CodeBlock";
import { Alert, Badge, Button, Card, EmptyState, KpiGrid, LoadingBlock, PageHeader, Tabs } from "../components/ui";
import { downloadAll } from "../lib/format";

type Field = { name: string; bits: string; reset: string; description: string };
type Reg = { name: string; offset: string; access: string; reset: string; mask: string; description: string; fields: Field[] };
type Result = {
  error?: string; block: string; data_width: number; addr_width: number; base_address: string;
  registers: Reg[]; outputs: Record<string, string>;
};

const ACCESS_TONE: Record<string, "info" | "good" | "warn" | "neutral"> = { RW: "info", RO: "good", WO: "warn", W1C: "neutral" };

export default function RegisterMap() {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [spec, setSpec] = useState("");
  const [tab, setTab] = useState("regs");
  const [open, setOpen] = useState<string | null>(null);
  const file = files?.[0] ?? null;
  useEffect(() => { setSpec(file?.text ?? ""); }, [file]);
  const { data, loading, error } = useAnalysis<Result>("/api/rtl/regmap", file ? { name: file.name, text: spec } : null, 400);
  const ok = data && !data.error;

  return (
    <>
      <PageHeader area="RTL design" title="Register Map" icon={Table2}
        description="Describe registers once in JSON. Get synthesizable Verilog, a C header for firmware and HTML documentation, always in sync. Edit the spec and everything updates live."
        actions={ok ? <Button variant="primary" icon={Download} onClick={() => downloadAll(data.outputs)}>Download all</Button> : undefined} />
      <Card className="mb-6">
        <FileSource label="Register spec" examples={["uart_regmap.json"]} accept=".json,.yaml,.yml" onChange={setFiles} />
      </Card>

      {error && <Alert tone="bad" title="Request failed">{error}</Alert>}
      {!file ? <EmptyState icon={Table2} title="No spec yet" text="Upload a JSON or YAML register spec." />
        : loading && !data ? <LoadingBlock />
        : (
          <>
            {data?.error && <Alert tone="bad" title="The spec has problems">
              <pre className="font-sans whitespace-pre-wrap">{data.error}</pre></Alert>}
            {ok && <KpiGrid items={[
              { label: "Block", value: data.block },
              { label: "Registers", value: data.registers.length, note: `${data.registers.reduce((s, r) => s + r.fields.length, 0)} fields` },
              { label: "Data width", value: `${data.data_width} bit` },
              { label: "Address width", value: `${data.addr_width} bit` },
              { label: "Base address", value: <span className="font-mono text-[20px]">{data.base_address}</span> },
            ]} />}
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "regs", label: "Registers", icon: Rows3, count: ok ? data.registers.length : undefined },
              { id: "doc", label: "Documentation", icon: FileText },
              { id: "v", label: "Verilog RTL", icon: Cpu },
              { id: "h", label: "C header", icon: Terminal },
              { id: "axil", label: "AXI-Lite slave", icon: ArrowLeftRight },
              { id: "tb", label: "AXI-Lite testbench", icon: FlaskConical },
              { id: "spec", label: "Spec editor", icon: Pencil },
            ]} />
            {tab === "spec" && (
              <Card title="Spec editor" subtitle="Changes are validated and applied as you type"
                actions={<Button variant="ghost" onClick={() => setSpec(file.text)}>Reset</Button>}>
                <textarea value={spec} onChange={(e) => setSpec(e.target.value)} spellCheck={false}
                  className="h-[480px] w-full resize-y rounded-lg border border-line bg-surface-2 p-4 font-mono text-[13px] leading-relaxed outline-none focus:border-brand focus:ring-3 focus:ring-brand/15" />
              </Card>
            )}
            {ok && tab === "regs" && (
              <Card bodyClass="p-4">
                <DataTable rows={data.registers} columns={[
                  { key: "offset", header: "Offset", mono: true },
                  { key: "name", header: "Register", render: (r) => (
                    <button className="font-mono font-semibold text-brand hover:underline" onClick={() => setOpen(open === r.name ? null : r.name)}>{r.name}</button>) },
                  { key: "access", header: "Access", render: (r) => <Badge tone={ACCESS_TONE[r.access]}>{r.access}</Badge> },
                  { key: "reset", header: "Reset", mono: true },
                  { key: "mask", header: "Mask", mono: true },
                  { key: "fields", header: "Fields", align: "right", value: (r) => r.fields.length, render: (r) => r.fields.length },
                  { key: "description", header: "Description", wrap: true },
                ]} />
                {open && (() => {
                  const r = data.registers.find((x) => x.name === open)!;
                  return (
                    <div className="mt-4 rounded-lg border border-line bg-surface-2 p-4">
                      <div className="mb-3 font-semibold">{r.name} <span className="font-normal text-muted">fields</span></div>
                      <DataTable rows={r.fields} dense columns={[
                        { key: "bits", header: "Bits", mono: true, render: (f) => `[${f.bits}]` },
                        { key: "name", header: "Field", mono: true },
                        { key: "reset", header: "Reset", mono: true },
                        { key: "description", header: "Description", wrap: true },
                      ]} />
                    </div>
                  );
                })()}
                <p className="mt-3 text-[13px] text-muted">Click a register name to see its bit fields.</p>
              </Card>
            )}
            {ok && tab === "doc" && (
              <iframe title="Register documentation" srcDoc={data.outputs[`${data.block}_regs.html`]} sandbox=""
                className="h-[680px] w-full rounded-xl border border-line bg-white shadow-card" />
            )}
            {ok && tab === "v" && <CodeBlock code={data.outputs[`${data.block}_regs.v`]} lang="verilog" filename={`${data.block}_regs.v`} />}
            {ok && tab === "h" && <CodeBlock code={data.outputs[`${data.block}_regs.h`]} lang="c" filename={`${data.block}_regs.h`} />}
            {ok && tab === "axil" && (
              <div className="space-y-4">
                <Alert tone="info" title="Ready-to-connect AXI4-Lite slave">
                  All registers inside one module with a standard <code className="font-mono">s_axil_*</code> interface: AW and W accepted in any order,
                  WSTRB byte enables, SLVERR for unmapped addresses. Connect it to your CPU / interconnect; the hardware-side ports are the same as in the plain register file.
                </Alert>
                <CodeBlock code={data.outputs[`${data.block}_axil.v`]} lang="verilog" filename={`${data.block}_axil.v`} />
              </div>
            )}
            {ok && tab === "tb" && (
              <div className="space-y-4">
                <Alert tone="info" title="Self-checking testbench">
                  Checks reset values, write/read-back, byte strobes, W1C set/clear and SLVERR, then prints TEST PASSED or TEST FAILED.
                  Run it with Icarus Verilog, then open the produced VCD in the AXI Protocol Checker to verify every handshake:
                  <code className="mt-2 block font-mono text-[12.5px]">iverilog -g2012 -o sim.out tb_{data.block}_axil.v {data.block}_axil.v &amp;&amp; vvp sim.out</code>
                </Alert>
                <CodeBlock code={data.outputs[`tb_${data.block}_axil.v`]} lang="verilog" filename={`tb_${data.block}_axil.v`} />
              </div>
            )}
          </>
        )}
    </>
  );
}
