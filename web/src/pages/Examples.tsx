import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Archive, Bug, Download, Eye, FileText, FolderOpen, Library, Search, Sparkles, Upload } from "lucide-react";
import { API_BASE, getJSON } from "../lib/api";
import { REPO_URL, toolByPath } from "../tools";
import { ExamplePreview, exampleDownloadUrl, openInToolUrl } from "../components/ExamplePreview";
import { GithubMark } from "../components/icons";
import { Alert, Badge, Chips, EmptyState, LoadingBlock, PageHeader, Toggle } from "../components/ui";
import { cx, type Tone } from "../lib/format";

type ExampleFile = {
  path: string; name: string; folder: string; kind: string; kind_label: string; area: string; size: number;
  title: string; description: string; highlight: string; tools: string[];
};
type Collection = { folder: string; title: string; description: string; tool: string; files: number };
type Catalog = { files: ExampleFile[]; collections: Collection[]; count: number; bytes: number };

const AREA_ORDER = ["RTL design", "Verification", "Physical design", "Analog"];
const FEATURED = ["lint_demo.v", "axi/axi_buggy.vcd", "signoff/uart_top.sdc", "pd/demo.def"];
const size = (b: number) => (b < 1024 ? `${b} B` : `${(b / 1024).toFixed(b < 10240 ? 1 : 0)} KB`);
const isBuggy = (f: ExampleFile) => /bug|finding|issue/i.test(f.highlight);

function highlightTone(h: string): Tone {
  if (/bug|finding|issue|wns/i.test(h)) return "bad";
  if (/clean|passes/i.test(h)) return "good";
  return "info";
}

function ExampleCard({ f, onPreview, featured }: { f: ExampleFile; onPreview: () => void; featured?: boolean }) {
  const tool = toolByPath(f.tools[0]);
  const Icon = tool?.icon ?? FileText;
  return (
    <div
      className={cx(
        "group flex flex-col rounded-xl border border-line bg-surface p-4 shadow-card transition hover:shadow-md",
        featured && "border-brand/40",
      )}
    >
      <div className="mb-3 flex items-start gap-3">
        <span className={cx("grid size-10 shrink-0 place-items-center rounded-xl", featured ? "bg-gradient-to-br from-[#6d8ff5] to-[#2f5bd3] text-white" : "bg-brand-soft text-brand")}>
          <Icon className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14.5px] font-semibold tracking-tight">{f.title}</div>
          <div className="truncate font-mono text-[11.5px] text-faint">{f.path}</div>
        </div>
        {f.highlight && <Badge tone={highlightTone(f.highlight)} className="shrink-0">{f.highlight}</Badge>}
      </div>
      <p className="mb-4 line-clamp-3 flex-1 text-[13px] leading-relaxed text-muted">{f.description}</p>
      <div className="mb-3 text-[11.5px] text-faint">
        {f.kind_label} · {size(f.size)}
      </div>
      <div className="flex items-center gap-1.5">
        {tool && (
          <Link
            to={openInToolUrl(tool.path, f.path)}
            className={cx(
              "inline-flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[12.5px] font-semibold transition",
              featured ? "bg-brand shadow-sm text-white hover:brightness-110" : "bg-brand-soft text-brand hover:bg-brand hover:text-white",
            )}
          >
            <span className="truncate">Open in {tool.title}</span>
            <ArrowRight className="size-3.5 shrink-0" />
          </Link>
        )}
        <button
          onClick={onPreview}
          title="Preview"
          aria-label={`Preview ${f.name}`}
          className="rounded-lg border border-line p-2 text-muted transition hover:bg-surface-3 hover:text-fg"
        >
          <Eye className="size-4" />
        </button>
        <a
          href={exampleDownloadUrl(f.path)}
          download
          title="Download"
          aria-label={`Download ${f.name}`}
          className="rounded-lg border border-line p-2 text-muted transition hover:bg-surface-3 hover:text-fg"
        >
          <Download className="size-4" />
        </a>
      </div>
    </div>
  );
}

export default function Examples() {
  const [data, setData] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [areas, setAreas] = useState<string[]>(AREA_ORDER);
  const [bugsOnly, setBugsOnly] = useState(false);
  const [preview, setPreview] = useState<ExampleFile | null>(null);

  useEffect(() => {
    getJSON<Catalog>("/api/examples/catalog").then(setData).catch((e) => setError((e as Error).message));
  }, []);

  const singles = useMemo(() => (data?.files ?? []).filter((f) => !data?.collections.some((c) => c.folder === f.folder)), [data]);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return singles.filter(
      (f) =>
        areas.includes(f.area) &&
        (!bugsOnly || isBuggy(f)) &&
        (!s || `${f.title} ${f.path} ${f.description} ${f.kind_label} ${f.highlight}`.toLowerCase().includes(s)),
    );
  }, [singles, q, areas, bugsOnly]);
  const featured = singles.filter((f) => FEATURED.includes(f.path));
  const filtering = q.trim() !== "" || bugsOnly || areas.length !== AREA_ORDER.length;

  return (
    <>
      <PageHeader
        area="Workspace"
        title="Examples Library"
        icon={Library}
        description="Every sample file that ships with the toolkit: RTL, waveforms, reports, constraints, layouts and netlists, many with planted bugs. Preview one, download it, or open it straight in the right tool."
        actions={
          <>
            <a
              href={`${REPO_URL}/tree/main/examples`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-3.5 py-2 text-[13.5px] font-semibold shadow-card hover:border-line-strong"
            >
              <GithubMark className="size-4" /> View on GitHub
            </a>
            <a
              href={`${API_BASE}/api/examples/zip`}
              className="bg-brand shadow-sm inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-[13.5px] font-semibold text-white hover:brightness-110"
            >
              <Archive className="size-4" /> Download all (.zip)
            </a>
          </>
        }
      />

      <div className="mb-7 grid gap-3 md:grid-cols-3">
        {[
          { icon: Eye, title: "1 · Preview", text: "Click a card to read the file and see what it contains." },
          { icon: Sparkles, title: "2 · Open in a tool", text: "One click loads it into the right tool and runs the analysis." },
          { icon: Upload, title: "3 · Or download", text: "Save it, edit it, and upload your version with the Upload tab." },
        ].map((s) => (
          <div key={s.title} className="flex gap-3 rounded-xl border border-line bg-surface/70 p-4 shadow-card">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
              <s.icon className="size-4.5" />
            </span>
            <div>
              <div className="text-[14px] font-semibold">{s.title}</div>
              <div className="text-[13px] text-muted">{s.text}</div>
            </div>
          </div>
        ))}
      </div>

      {error && <Alert tone="bad" title="Could not load the examples">{error}</Alert>}
      {!data ? (
        !error && <LoadingBlock label="Loading examples…" />
      ) : (
        <>
          {!filtering && featured.length > 0 && (
            <>
              <h2 className="mb-3 flex items-center gap-2 text-[17px] font-semibold tracking-tight">
                <Sparkles className="size-4.5 text-brand" /> Start here
                <span className="text-[13px] font-normal text-muted">files with planted bugs show each tool at its best</span>
              </h2>
              <div className="mb-9 grid gap-4 md:grid-cols-2">
                {FEATURED.map((p) => featured.find((f) => f.path === p)).filter(Boolean).map((f) => (
                  <ExampleCard key={f!.path} f={f!} featured onPreview={() => setPreview(f!)} />
                ))}
              </div>
            </>
          )}

          <div className="sticky top-14 z-10 -mx-1 mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface/85 p-3 shadow-card backdrop-blur-xl">
            <div className="relative min-w-60 flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={`Search ${data.count} files…`}
                className="w-full rounded-xl border border-line bg-surface py-2 pr-3 pl-9 text-[13.5px] outline-none placeholder:text-faint focus:border-brand focus:ring-4 focus:ring-brand/12"
              />
            </div>
            <Chips
              selected={areas}
              onChange={setAreas}
              options={AREA_ORDER.map((a) => ({ value: a, label: a, count: singles.filter((f) => f.area === a).length }))}
            />
            <div className="ml-auto">
              <Toggle checked={bugsOnly} onChange={setBugsOnly} label="Planted bugs only" />
            </div>
          </div>

          {shown.length === 0 ? (
            <EmptyState icon={Bug} title="No example matches" text="Clear the search or select more design areas." />
          ) : (
            AREA_ORDER.filter((a) => shown.some((f) => f.area === a)).map((a) => (
              <section key={a} className="mb-9">
                <h2 className="mb-3 flex items-center gap-2 text-[17px] font-semibold tracking-tight">
                  {a}
                  <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[12px] font-medium text-muted">
                    {shown.filter((f) => f.area === a).length}
                  </span>
                </h2>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {shown.filter((f) => f.area === a).map((f) => (
                    <ExampleCard key={f.path} f={f} onPreview={() => setPreview(f)} />
                  ))}
                </div>
              </section>
            ))
          )}

          {!filtering && (
            <section className="mb-4">
              <h2 className="mb-3 text-[17px] font-semibold tracking-tight">Regression log sets</h2>
              <div className="grid gap-4 lg:grid-cols-2">
                {data.collections.map((c) => {
                  const files = data.files.filter((f) => f.folder === c.folder);
                  const tool = toolByPath(c.tool);
                  return (
                    <div key={c.folder} className="rounded-xl border border-line bg-surface p-5 shadow-card">
                      <div className="mb-2 flex items-center gap-3">
                        <span className="grid size-10 place-items-center rounded-xl bg-brand-soft text-brand">
                          <FolderOpen className="size-5" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="text-[15px] font-semibold">{c.title}</div>
                          <div className="font-mono text-[11.5px] text-faint">examples/{c.folder}/ · {c.files} logs</div>
                        </div>
                        {tool && (
                          <Link
                            to={c.tool}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-soft px-2.5 py-1.5 text-[12.5px] font-semibold text-brand transition hover:bg-brand hover:text-white"
                          >
                            Open in {tool.title} <ArrowRight className="size-3.5" />
                          </Link>
                        )}
                      </div>
                      <p className="mb-3 text-[13px] text-muted">{c.description}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {files.map((f) => (
                          <button
                            key={f.path}
                            onClick={() => setPreview(f)}
                            className="rounded-lg border border-line bg-surface-2 px-2 py-1 font-mono text-[11.5px] text-muted transition hover:border-brand/40 hover:text-fg"
                          >
                            {f.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}

      {preview && (
        <ExamplePreview
          path={preview.path}
          title={preview.title}
          description={preview.description}
          tools={preview.tools}
          onClose={() => setPreview(null)}
        />
      )}
    </>
  );
}
