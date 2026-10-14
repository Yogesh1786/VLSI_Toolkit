import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, CircleCheck, CircleX, FolderGit2, FolderOpen, History, Play, RefreshCw, RotateCcw, TriangleAlert,
} from "lucide-react";
import { postJSON } from "../lib/api";
import { fmtAgo, fmtSize, openWorkspace, refreshWorkspace, resetWorkspace, useWorkspace, type WsFile } from "../lib/workspace";
import { toolByPath } from "../tools";
import { Alert, Badge, Button, Card, EmptyState, LoadingBlock, PageHeader, Spinner, TextInput, Toggle } from "../components/ui";
import { cx, TONE_HEX } from "../lib/format";

type Check = { name: string; status: "pass" | "warn" | "fail"; value: string; detail: string; tool: string | null };
type Analysis = {
  root: string; checks: Check[]; metrics: Record<string, number>; errors: string[]; health_score: number | null;
  files_analyzed: number; seconds: number; snapshot_id?: number;
};

const STATUS = {
  pass: { icon: CircleCheck, color: "text-good", ring: TONE_HEX.good, label: "Pass" },
  warn: { icon: TriangleAlert, color: "text-warn", ring: TONE_HEX.warn, label: "Warning" },
  fail: { icon: CircleX, color: "text-bad", ring: TONE_HEX.bad, label: "Fail" },
};

function ScoreRing({ score }: { score: number }) {
  const r = 46, c = 2 * Math.PI * r;
  const color = score >= 80 ? TONE_HEX.good : score >= 50 ? TONE_HEX.warn : TONE_HEX.bad;
  return (
    <svg viewBox="0 0 120 120" className="size-32 shrink-0">
      <circle cx="60" cy="60" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="11" />
      <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round"
        strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 60 60)" />
      <text x="60" y="60" textAnchor="middle" fontSize="30" fontWeight="700" fill="var(--text)">{score}</text>
      <text x="60" y="80" textAnchor="middle" fontSize="11" fill="var(--faint)">health</text>
    </svg>
  );
}

function KindCard({ label, files, tools }: { label: string; files: WsFile[]; tools: string[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? files : files.slice(0, 4);
  return (
    <Card title={<span className="flex items-center gap-2">{label}<Badge tone="info">{files.length}</Badge></span>}
      actions={<div className="flex flex-wrap gap-1.5">{tools.map((t) => {
        const tool = toolByPath(t);
        return tool ? <Link key={t} to={`${t}?ws=${encodeURIComponent(files.map((f) => f.path).slice(0, 200).join(","))}`}
          className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[12px] font-medium text-muted hover:border-brand/50 hover:text-brand">
          <tool.icon className="size-3.5" />{tool.title}</Link> : null;
      })}</div>} bodyClass="p-0">
      <div>
        {shown.map((f) => (
          <div key={f.path} className="group flex items-center gap-3 border-b border-line px-5 py-2 last:border-0">
            <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={f.path}>{f.path}</span>
            <span className="shrink-0 text-[11.5px] text-faint">{fmtSize(f.size)} · {fmtAgo(f.modified)}</span>
            {tools[0] && <Link to={`${tools[0]}?ws=${encodeURIComponent(f.path)}`} title={`Open in ${toolByPath(tools[0])?.title}`}
              className="text-faint opacity-0 group-hover:opacity-100 hover:text-brand"><ArrowRight className="size-4" /></Link>}
          </div>
        ))}
        {files.length > 4 && (
          <button onClick={() => setAll(!all)} className="w-full px-5 py-2 text-left text-[12.5px] font-medium text-brand hover:bg-surface-2">
            {all ? "Show less" : `Show all ${files.length} files`}
          </button>
        )}
      </div>
    </Card>
  );
}

export default function Workspace() {
  const { ws, loading, error } = useWorkspace();
  const [path, setPath] = useState("");
  const [openError, setOpenError] = useState<string | null>(null);
  const [save, setSave] = useState(true);
  const [label, setLabel] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const open = async (p: string) => {
    setOpenError(null); setAnalysis(null);
    try { await openWorkspace(p); setPath(""); } catch (e) { setOpenError((e as Error).message); }
  };
  const analyze = async () => {
    setAnalyzing(true); setAnalyzeError(null);
    try { setAnalysis(await postJSON<Analysis>("/api/workspace/analyze", { save, label })); }
    catch (e) { setAnalyzeError((e as Error).message); }
    finally { setAnalyzing(false); }
  };

  const groups = ws ? Object.keys(ws.kinds).filter((k) => ws.counts[k]).map((k) => ({
    kind: k, label: ws.kinds[k], files: ws.files.filter((f) => f.kind === k), tools: ws.tools[k] ?? [] })) : [];

  return (
    <>
      <PageHeader area="Workspace" title="Project Workspace" icon={FolderGit2}
        description="Point the toolkit at your project folder once: design files are found and sorted automatically, every tool can pick files from it, and one click analyzes everything." />

      <Card className="mb-6" title="Project folder" subtitle={ws?.is_default && !ws.hosted ? "Showing the bundled examples. Open your own project folder below." : undefined}
        actions={ws && <div className="flex gap-2">
          <Button variant="ghost" icon={RefreshCw} onClick={() => refreshWorkspace()} disabled={loading}>Rescan</Button>
          {!ws.is_default && <Button variant="ghost" icon={RotateCcw} onClick={() => resetWorkspace()}>Use examples</Button>}
        </div>}>
        {ws && (
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg bg-surface-2 px-4 py-3">
            <FolderOpen className="size-5 text-brand" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold">{ws.name}</div>
              <div className="truncate font-mono text-[12.5px] text-muted">{ws.root}</div>
            </div>
            <span className="text-[13px] text-muted">{ws.files.length} design files{ws.truncated && " (limit reached)"} · scanned {fmtAgo(ws.scanned_at)}</span>
          </div>
        )}
        {ws?.hosted ? (
          <Alert tone="info" title="Online demo">This hosted version shows the bundled example project. To analyze your own project folder,
            run the toolkit on your computer (start_app.bat); for single files, use Upload on any tool page.</Alert>
        ) : (
          <div className="flex flex-wrap gap-2">
            <div className="min-w-72 flex-1"><TextInput mono value={path} onChange={setPath} placeholder="C:\Users\you\projects\my_chip  (paste a folder path)" /></div>
            <Button variant="primary" icon={FolderOpen} onClick={() => path.trim() && open(path)} disabled={!path.trim() || loading}>Open folder</Button>
          </div>
        )}
        {openError && <div className="mt-3"><Alert tone="bad">{openError}</Alert></div>}
        {ws && ws.recent.some((r) => r !== ws.root) && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12.5px]">
            <span className="text-faint">Recent:</span>
            {ws.recent.filter((r) => r !== ws.root).map((r) => (
              <button key={r} onClick={() => open(r)} className="rounded-md border border-line bg-surface px-2 py-0.5 font-mono text-muted hover:border-brand/50 hover:text-brand" title={r}>
                {r.split(/[\\/]/).pop()}</button>
            ))}
          </div>
        )}
        <p className="mt-3 text-[12.5px] text-faint">Tip: in Windows Explorer, click the address bar of your project folder and copy the path. Files are read only on this computer.</p>
      </Card>

      {error && <Alert tone="bad" title="Could not load the workspace">{error}</Alert>}
      {!ws && loading ? <LoadingBlock label="Scanning folder…" /> : ws && (
        <>
          <Card className="mb-6" title="Analyze workspace" subtitle="Runs lint, hierarchy, regression, timing, AXI, floorplan and netlist checks on everything found"
            actions={<div className="flex flex-wrap items-center gap-3">
              <Toggle checked={save} onChange={setSave} label="Save to history" />
              {save && <div className="w-44"><TextInput value={label} onChange={setLabel} placeholder="label, e.g. nightly" /></div>}
              <Button variant="primary" icon={analyzing ? undefined : Play} onClick={analyze} disabled={analyzing || !ws.files.length}>
                {analyzing ? <><Spinner className="text-white" /> Analyzing…</> : "Analyze"}</Button>
            </div>}>
            {analyzeError && <Alert tone="bad">{analyzeError}</Alert>}
            {!analysis && !analyzeError && <p className="text-[14px] text-muted">Press <b>Analyze</b> for a health check of the whole project.{save && " The result is saved, so you can follow the trend over time."}</p>}
            {analysis && (
              <div className="flex flex-wrap items-start gap-6">
                {analysis.health_score != null && <ScoreRing score={analysis.health_score} />}
                <div className="min-w-72 flex-1 space-y-2">
                  {analysis.checks.map((c) => {
                    const S = STATUS[c.status];
                    return (
                      <div key={c.name} className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5">
                        <S.icon className={cx("size-5 shrink-0", S.color)} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-baseline gap-x-2"><span className="font-semibold">{c.name}</span>
                            <span className={cx("text-[13.5px] font-medium", S.color)}>{c.value}</span></div>
                          <div className="truncate text-[12.5px] text-muted">{c.detail}</div>
                        </div>
                        {c.tool && <Link to={c.tool} className="shrink-0 text-[12.5px] font-medium text-brand hover:underline">Open</Link>}
                      </div>
                    );
                  })}
                  {analysis.errors.map((e) => <Alert key={e} tone="warn">{e}</Alert>)}
                  <div className="flex flex-wrap items-center gap-3 pt-1 text-[12.5px] text-faint">
                    {analysis.files_analyzed} files analyzed in {analysis.seconds} s
                    {analysis.snapshot_id && <Link to="/trends" className="inline-flex items-center gap-1 font-medium text-brand hover:underline"><History className="size-3.5" />Saved: view trends</Link>}
                  </div>
                </div>
              </div>
            )}
          </Card>

          {groups.length === 0 ? <EmptyState icon={FolderGit2} title="No design files found" text="Supported: .v .sv, logs, timing reports, .vcd, .def .lef .lib, SPICE netlists, register specs, SDC and synthesis/power reports." /> : (
            <>
              <h2 className="mb-3 text-[15px] font-semibold">Files found</h2>
              <div className="grid gap-5 lg:grid-cols-2">
                {groups.map((g) => <KindCard key={g.kind} label={g.label} files={g.files} tools={g.tools} />)}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
