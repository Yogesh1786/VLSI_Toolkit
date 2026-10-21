// Dialog that shows a bundled example file, with Download and "Open in <tool>" actions.
// Used by the file chooser of every tool and by the Examples Library page.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ArrowRight, Download, FileText, X } from "lucide-react";
import { API_BASE, loadExample } from "../lib/api";
import { toolByPath } from "../tools";
import { CodeBlock, langFor } from "./CodeBlock";
import { Spinner } from "./ui";

/** Address that downloads one example file (works on the hosted site too). */
export const exampleDownloadUrl = (path: string) => `${API_BASE}/api/examples/download?path=${encodeURIComponent(path)}`;

/** Link that opens a tool with this example already loaded. */
export const openInToolUrl = (tool: string, path: string) => (tool === "/compare" ? tool : `${tool}?ex=${encodeURIComponent(path)}`);

export function ExamplePreview({
  path,
  title,
  description,
  tools = [],
  onClose,
}: {
  path: string;
  title?: string;
  description?: string;
  tools?: string[];
  onClose: () => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    loadExample(path)
      .then((f) => alive && setText(f.text))
      .catch((e) => alive && setError((e as Error).message));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      alive = false;
      window.removeEventListener("keydown", onKey);
    };
  }, [path, onClose]);

  const name = path.split("/").pop() ?? path;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-[#050816]/55 p-3 pt-[6vh] backdrop-blur-sm sm:p-6" onClick={onClose}>
      <div
        role="dialog"
        aria-label={`Example ${name}`}
        className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-4 border-b border-line px-5 py-4">
          <div className="bg-gradient-to-br from-[#6d8ff5] to-[#2f5bd3] grid size-10 shrink-0 place-items-center rounded-xl text-white">
            <FileText className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[16px] font-semibold tracking-tight">{title ?? name}</div>
            <div className="font-mono text-[12px] text-faint">examples/{path}</div>
            {description && <p className="mt-1.5 text-[13.5px] text-muted">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-faint hover:bg-surface-3 hover:text-fg" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {error ? (
            <p className="py-10 text-center text-bad">{error}</p>
          ) : text == null ? (
            <div className="flex items-center justify-center gap-2 py-16 text-muted">
              <Spinner /> Loading…
            </div>
          ) : (
            <CodeBlock code={text} filename={name} lang={langFor(name)} maxHeight={520} download={false} />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-surface-2 px-5 py-3">
          <a
            href={exampleDownloadUrl(path)}
            download={name}
            className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-3.5 py-2 text-[13.5px] font-semibold shadow-card hover:border-line-strong"
          >
            <Download className="size-4" /> Download
          </a>
          <div className="ml-auto flex flex-wrap gap-2">
            {tools.slice(0, 3).map((t, i) => {
              const tool = toolByPath(t);
              if (!tool) return null;
              return (
                <Link
                  key={t}
                  to={openInToolUrl(t, path)}
                  onClick={onClose}
                  className={
                    i === 0
                      ? "bg-brand shadow-sm inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-[13.5px] font-semibold text-white hover:brightness-110"
                      : "inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-3.5 py-2 text-[13.5px] font-semibold shadow-card hover:border-line-strong"
                  }
                >
                  <tool.icon className="size-4" /> Open in {tool.title}
                  {i === 0 && <ArrowRight className="size-4" />}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
