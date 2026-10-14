// Code viewer: line numbers, light syntax coloring, copy and download buttons.
import { Fragment, useMemo, type ReactNode } from "react";
import { FileCode } from "lucide-react";
import { CopyButton, DownloadButton } from "./ui";
import { cx } from "../lib/format";

type Lang = "verilog" | "python" | "c" | "text" | "bash";

const KEYWORDS: Record<Lang, string[]> = {
  verilog: (
    "module endmodule input output inout wire reg logic bit signed unsigned parameter localparam assign always " +
    "always_ff always_comb always_latch begin end if else case casez casex endcase default for while initial posedge " +
    "negedge or and not integer genvar generate endgenerate function endfunction task endtask unique priority typedef " +
    "struct enum"
  ).split(" "),
  python: (
    "import from def return async await for in if elif else while with as class try except finally True False " +
    "None and or not lambda yield pass break continue"
  ).split(" "),
  c: "include define ifndef ifdef endif if else return int uint32_t uint64_t uint8_t void static const volatile unsigned struct typedef".split(
    " ",
  ),
  bash: [],
  text: [],
};

const TOKEN_RE: Record<Lang, RegExp> = {
  verilog:
    /(\/\/.*$)|("(?:\\.|[^"\\])*")|(\$\w+|`\w+)|(\b\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g,
  python:
    /(#.*$)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(@\w+)|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g,
  c: /(\/\*.*?\*\/|\/\/.*$)|("(?:\\.|[^"\\])*")|(#\w+)|(\b0x[0-9a-fA-F]+[uUlL]*|\b\d+[uUlL]*\b)|(\b[A-Za-z_]\w*\b)/g,
  bash: /(#.*$)|("(?:\\.|[^"\\])*")|()|()|()/g,
  text: /()()()()()/g,
};

function highlight(line: string, lang: Lang): ReactNode[] {
  if (lang === "text") return [line];
  const out: ReactNode[] = [];
  const re = new RegExp(TOKEN_RE[lang].source, "g");
  let last = 0;
  let m: RegExpExecArray | null;
  const kw = new Set(KEYWORDS[lang]);
  while ((m = re.exec(line))) {
    if (m[0] === "") {
      re.lastIndex++;
      continue;
    }
    if (m.index > last) out.push(line.slice(last, m.index));
    const [tok, com, str, sys, num, word] = m;
    const cls = com
      ? "tok-com"
      : str
        ? "tok-str"
        : sys
          ? "tok-sys"
          : num
            ? "tok-num"
            : word && kw.has(word)
              ? "tok-kw"
              : "";
    out.push(
      cls ? (
        <span key={m.index} className={cls}>
          {tok}
        </span>
      ) : (
        tok
      ),
    );
    last = m.index + tok.length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

export function CodeBlock({
  code,
  lang = "text",
  filename,
  maxHeight = 560,
  download = true,
  highlightLines = [],
}: {
  code: string;
  lang?: Lang;
  filename?: string;
  maxHeight?: number;
  download?: boolean;
  highlightLines?: number[];
}) {
  const lines = useMemo(() => code.replace(/\n$/, "").split("\n"), [code]);
  const marked = useMemo(() => new Set(highlightLines), [highlightLines]);
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
      <div className="flex items-center gap-2 border-b border-line bg-surface-2 px-3 py-1.5">
        <FileCode className="size-4 text-faint" />
        <span className="flex-1 truncate font-mono text-[12.5px] text-muted">
          {filename ?? lang}
        </span>
        <span className="text-[12px] text-faint">{lines.length} lines</span>
        <CopyButton text={code} />
        {download && filename && (
          <DownloadButton name={filename} text={code} label="Download" />
        )}
      </div>
      <div className="overflow-auto" style={{ maxHeight }}>
        <pre className="grid min-w-fit grid-cols-[auto_1fr] font-mono text-[12.8px] leading-[1.6]">
          {lines.map((line, i) => (
            <Fragment key={i}>
              <span
                className={cx(
                  "sticky left-0 select-none border-r border-line bg-surface px-3 text-right text-faint tabular-nums",
                  marked.has(i + 1) && "bg-warn/15 text-warn",
                )}
              >
                {i + 1}
              </span>
              <code
                className={cx(
                  "px-4 whitespace-pre",
                  marked.has(i + 1) && "bg-warn/10",
                )}
              >
                {highlight(line, lang)}
                {"\n"}
              </code>
            </Fragment>
          ))}
        </pre>
      </div>
    </div>
  );
}
