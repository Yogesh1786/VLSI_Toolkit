// File chooser: bundled example, files from the project workspace, or upload (drag & drop).
// Reports the chosen files to the parent page. A link like /lint?ws=rtl/top.sv opens the
// page with that workspace file already selected.
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, FileText, FolderGit2, FolderOpen, Upload, X } from "lucide-react";
import { loadExample, type SourceFile } from "../lib/api";
import { fmtAgo, fmtSize, loadWorkspaceFile, matchingFiles, useWorkspace } from "../lib/workspace";
import { Segmented, Spinner } from "./ui";
import { cx } from "../lib/format";

type Mode = "example" | "workspace" | "upload";

export function FileSource({ label, examples, accept, multiple, onChange, wsKinds }: {
  label: string;
  examples: string[];            // example paths under examples/
  accept?: string;               // e.g. ".v,.sv"
  multiple?: boolean;
  onChange: (files: SourceFile[] | null) => void;
  wsKinds?: string[];            // workspace file kinds to offer (default: match by extension)
}) {
  const { ws } = useWorkspace();
  const [params] = useSearchParams();
  const candidates = useMemo(() => (ws && !ws.is_default ? matchingFiles(ws, accept, wsKinds) : []), [ws, accept, wsKinds]);
  const linked = useMemo(() => {
    const want = (params.get("ws") ?? "").split(",").filter(Boolean);
    return candidates.filter((f) => want.includes(f.path)).map((f) => f.path);
  }, [params, candidates]);

  const [mode, setMode] = useState<Mode>("example");
  const [picked, setPicked] = useState<string[]>([]);
  const [uploaded, setUploaded] = useState<SourceFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [drag, setDrag] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const examplesKey = examples.join("|");

  // a ?ws= link selects workspace files automatically
  useEffect(() => {
    if (linked.length) { setMode("workspace"); setPicked(multiple ? linked : linked.slice(0, 1)); }
  }, [linked.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  // default selection when switching to the workspace
  useEffect(() => {
    if (mode === "workspace" && !picked.length && candidates.length)
      setPicked(multiple ? candidates.slice(0, 200).map((f) => f.path) : [candidates[0].path]);
  }, [mode, candidates]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    const deliver = (p: Promise<SourceFile[]>) => {
      setLoading(true);
      p.then((files) => !cancelled && onChange(files.length ? files : null))
        .catch(() => !cancelled && onChange(null))
        .finally(() => !cancelled && setLoading(false));
    };
    if (mode === "example") deliver(Promise.all(examples.map(loadExample)).then((fs) => fs.map(({ name, text }) => ({ name, text }))));
    else if (mode === "workspace") deliver(Promise.all(picked.map(loadWorkspaceFile)).then((fs) => fs.map(({ path, text }) => ({ name: path, text }))));
    else onChange(uploaded.length ? uploaded : null);
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, examplesKey, uploaded, picked.join("|")]);

  const readFiles = async (list: FileList | null) => {
    if (!list?.length) return;
    const files = await Promise.all(Array.from(list).map(async (f) => ({ name: f.name, text: await f.text() })));
    setUploaded((prev) => (multiple ? [...prev.filter((p) => !files.some((f) => f.name === p.name)), ...files] : files.slice(0, 1)));
  };
  const toggle = (path: string) => setPicked((p) => (p.includes(path) ? p.filter((x) => x !== path) : [...p, path]));

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-[13px] font-medium text-muted">{label}</span>
        <Segmented size="sm" value={mode} onChange={setMode} options={[
          { value: "example", label: multiple ? "Examples" : "Example", icon: FolderOpen },
          ...(candidates.length ? [{ value: "workspace" as Mode, label: `Workspace (${candidates.length})`, icon: FolderGit2 }] : []),
          { value: "upload", label: "Upload", icon: Upload },
        ]} />
        {loading && <Spinner />}
      </div>

      {mode === "example" && (
        <div className="flex flex-wrap items-center gap-2">
          {(showAll || examples.length <= 4 ? examples : examples.slice(0, 3)).map((e) => (
            <span key={e} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface-2 px-2.5 py-1 font-mono text-[12px] text-muted">
              <FileText className="size-3.5" />examples/{e}
            </span>
          ))}
          {examples.length > 4 && (
            <button onClick={() => setShowAll((s) => !s)} className="text-[12.5px] font-medium text-brand hover:underline">
              {showAll ? "Show less" : `+ ${examples.length - 3} more (${examples.length} files)`}
            </button>
          )}
        </div>
      )}

      {mode === "workspace" && ws && (
        <div>
          <div className="mb-2 flex items-center gap-2 text-[12.5px] text-faint">
            <FolderGit2 className="size-3.5" /><span className="truncate font-mono">{ws.root}</span>
            {multiple && (
              <span className="ml-auto flex shrink-0 gap-3">
                <button className="font-medium text-brand hover:underline" onClick={() => setPicked(candidates.map((f) => f.path))}>All</button>
                <button className="font-medium text-brand hover:underline" onClick={() => setPicked([])}>None</button>
              </span>
            )}
          </div>
          <div className="max-h-56 overflow-y-auto rounded-lg border border-line">
            {candidates.map((f) => {
              const on = picked.includes(f.path);
              return (
                <button key={f.path} onClick={() => (multiple ? toggle(f.path) : setPicked([f.path]))}
                  className={cx("flex w-full items-center gap-3 border-b border-line px-3 py-1.5 text-left last:border-0 hover:bg-surface-2",
                    on && "bg-brand-soft/60")}>
                  <span className={cx("grid size-4 shrink-0 place-items-center border", multiple ? "rounded" : "rounded-full",
                    on ? "border-brand bg-brand text-white" : "border-line-strong")}>{on && <Check className="size-3" strokeWidth={3} />}</span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]">{f.path}</span>
                  <span className="shrink-0 text-[11.5px] text-faint">{fmtSize(f.size)} · {fmtAgo(f.modified)}</span>
                </button>
              );
            })}
          </div>
          {multiple && <div className="mt-1.5 text-[12px] text-faint">{picked.length} of {candidates.length} selected</div>}
        </div>
      )}

      {mode === "upload" && (
        <div>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); readFiles(e.dataTransfer.files); }}
            onClick={() => input.current?.click()}
            className={cx("flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 text-center transition",
              drag ? "border-brand bg-brand-soft" : "border-line-strong hover:border-brand/60 hover:bg-surface-2")}>
            <Upload className="mb-2 size-5 text-brand" />
            <div className="text-[14px] font-medium">Drop {multiple ? "files" : "a file"} here or <span className="text-brand">browse</span></div>
            <div className="mt-0.5 text-[12.5px] text-faint">{accept ? accept.split(",").join("  ") : "any text file"} · stays on this computer</div>
            <input ref={input} type="file" className="hidden" accept={accept} multiple={multiple}
              onChange={(e) => { readFiles(e.target.files); e.target.value = ""; }} />
          </div>
          {uploaded.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {uploaded.map((f) => (
                <span key={f.name} className="inline-flex items-center gap-1.5 rounded-md border border-brand/30 bg-brand-soft px-2.5 py-1 text-[12.5px] text-brand">
                  <FileText className="size-3.5" />{f.name}
                  <span className="text-faint">{(f.text.length / 1024).toFixed(1)} KB</span>
                  <button onClick={() => setUploaded((u) => u.filter((x) => x.name !== f.name))} className="hover:text-bad" title="Remove">
                    <X className="size-3.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
