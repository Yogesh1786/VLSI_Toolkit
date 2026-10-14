// Sortable, searchable table with a sticky header.
import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown, Search } from "lucide-react";
import { cx } from "../lib/format";

export type Column<T> = {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  value?: (row: T) => string | number | null | undefined; // used for sorting / searching
  align?: "left" | "right" | "center";
  width?: string;
  mono?: boolean;
  wrap?: boolean;
};

export function DataTable<T>({ rows, columns, searchable, maxHeight = 520, empty = "No rows", initialSort, dense }: {
  rows: T[]; columns: Column<T>[]; searchable?: boolean; maxHeight?: number; empty?: string;
  initialSort?: { key: string; dir: "asc" | "desc" }; dense?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState(initialSort ?? null);

  const valueOf = (row: T, col: Column<T>) =>
    col.value ? col.value(row) : ((row as Record<string, unknown>)[col.key] as string | number | null | undefined);

  const shown = useMemo(() => {
    let out = rows;
    if (query.trim()) {
      const q = query.toLowerCase();
      out = out.filter((r) => columns.some((c) => String(valueOf(r, c) ?? "").toLowerCase().includes(q)));
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col) {
        out = [...out].sort((a, b) => {
          const va = valueOf(a, col), vb = valueOf(b, col);
          if (va == null) return 1;
          if (vb == null) return -1;
          const r = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), undefined, { numeric: true });
          return sort.dir === "asc" ? r : -r;
        });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, query, sort, columns]);

  const toggleSort = (key: string) =>
    setSort((s) => (s?.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));

  return (
    <div>
      {searchable && (
        <div className="mb-3 flex items-center gap-3">
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search…"
              className="w-full rounded-lg border border-line bg-surface py-1.5 pr-3 pl-9 text-[13.5px] outline-none focus:border-brand focus:ring-3 focus:ring-brand/15" />
          </div>
          <span className="text-[13px] text-faint">{shown.length} of {rows.length}</span>
        </div>
      )}
      <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
        <table className="w-full border-collapse text-[13.5px]">
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr>
              {columns.map((c) => (
                <th key={c.key} style={{ width: c.width }}
                  className={cx("border-b border-line px-3 py-2.5 text-[12px] font-semibold whitespace-nowrap text-muted",
                    c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "text-left")}>
                  <button onClick={() => toggleSort(c.key)} className="inline-flex items-center gap-1 hover:text-fg">
                    {c.header}
                    {sort?.key === c.key ? (sort.dir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)
                      : <ChevronsUpDown className="size-3 opacity-40" />}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-muted">{empty}</td></tr>
            )}
            {shown.map((row, i) => (
              <tr key={i} className="border-b border-line last:border-0 hover:bg-surface-2">
                {columns.map((c) => (
                  <td key={c.key}
                    className={cx("px-3 align-top", dense ? "py-1.5" : "py-2.5",
                      c.align === "right" ? "text-right tabular-nums" : c.align === "center" ? "text-center" : "text-left",
                      c.mono && "font-mono text-[12.5px]", c.wrap ? "break-words" : "whitespace-nowrap")}>
                    {c.render ? c.render(row) : String(valueOf(row, c) ?? "–")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
