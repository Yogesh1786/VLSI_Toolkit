import { useEffect, useMemo, useRef, useState } from "react";
import { Eye, EyeOff, Layers, Maximize2, Network, Shapes, Type, Upload, ZoomIn, ZoomOut } from "lucide-react";
import { getJSON, postJSON } from "../lib/api";
import { DataTable } from "../components/DataTable";
import { Alert, Button, Card, EmptyState, KpiGrid, LoadingBlock, PageHeader, Segmented, Select, Tabs, Toggle } from "../components/ui";
import { cx, fmtInt } from "../lib/format";

type Layer = { layer: number; datatype: number; name: string; polygons: number; area: number; path: string };
type Node = { name: string; polygons: number; count?: number; children: Node[] };
type Result = {
  file: string; library: string; unit: number; cells: string[]; top_cells: string[]; cell: string;
  bbox: { x0: number; y0: number; x1: number; y1: number; width: number; height: number };
  layers: Layer[]; labels: { text: string; x: number; y: number; layer: number }[];
  hierarchy: Node; usage: { cell: string; instances: number }[]; instances: number;
  polygons: number; shown_polygons: number; truncated: boolean;
};

// distinct colours for layers (cycled), drawn semi-transparent so overlaps stay visible
const COLORS = ["#3b74e6", "#e08a00", "#1f9d55", "#c2417a", "#7c4fd6", "#1aa3a3", "#d64545", "#8a6d1f", "#4c9a2a", "#b84fd6", "#2f8fcf", "#e0559b"];

function toBase64(buf: ArrayBuffer) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function Tree({ node, depth = 0 }: { node: Node; depth?: number }) {
  return (
    <div>
      <div className="flex items-center gap-2 py-1 text-[13px]" style={{ paddingLeft: depth * 18 }}>
        <Network className="size-3.5 text-faint" />
        <span className="font-mono font-medium">{node.name}</span>
        {node.count != null && <span className="rounded bg-brand-soft px-1.5 text-[11px] font-semibold text-brand">×{node.count}</span>}
        <span className="text-[12px] text-faint">{node.polygons} own shapes</span>
      </div>
      {node.children.map((c) => <Tree key={c.name} node={c} depth={depth + 1} />)}
    </div>
  );
}

function LayoutView({ data, hidden, showLabels }: { data: Result; hidden: Set<string>; showLabels: boolean }) {
  const { x0, y0, width, height } = data.bbox;
  const pad = Math.max(width, height) * 0.03 || 1;
  // SVG y points down: the server already negated y, so the box spans -y1 .. -y0
  const full = { x: x0 - pad, y: -(y0 + height) - pad, w: width + 2 * pad, h: height + 2 * pad };
  const [vb, setVb] = useState(full);
  const drag = useRef<{ x: number; y: number; vb: typeof full } | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  useEffect(() => setVb(full), [data.cell, data.file]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoom = (f: number, cx?: number, cy?: number) =>
    setVb((v) => {
      const px = cx ?? v.x + v.w / 2, py = cy ?? v.y + v.h / 2;
      return { x: px - (px - v.x) * f, y: py - (py - v.y) * f, w: v.w * f, h: v.h * f };
    });
  const toUser = (e: { clientX: number; clientY: number }) => {
    const r = svg.current!.getBoundingClientRect();
    const s = Math.max(vb.w / r.width, vb.h / r.height);
    const ox = (r.width * s - vb.w) / 2, oy = (r.height * s - vb.h) / 2;
    return { x: vb.x - ox + (e.clientX - r.left) * s, y: vb.y - oy + (e.clientY - r.top) * s, s };
  };

  return (
    <div className="relative overflow-hidden rounded-xl border border-line bg-[#0b1020]">
      <svg
        ref={svg}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        className="h-[560px] w-full cursor-grab active:cursor-grabbing"
        onWheel={(e) => { const p = toUser(e); zoom(e.deltaY > 0 ? 1.2 : 1 / 1.2, p.x, p.y); }}
        onMouseDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, vb }; }}
        onMouseMove={(e) => {
          if (!drag.current) return;
          const { s } = toUser(e);
          const d = drag.current;
          setVb({ ...d.vb, x: d.vb.x - (e.clientX - d.x) * s, y: d.vb.y - (e.clientY - d.y) * s });
        }}
        onMouseUp={() => { drag.current = null; }}
        onMouseLeave={() => { drag.current = null; }}
      >
        {data.layers.map((l, i) => {
          const key = `${l.layer}/${l.datatype}`;
          if (hidden.has(key) || !l.path) return null;
          const c = COLORS[i % COLORS.length];
          const outline = l.name === "prBoundary";
          return <path key={key} d={l.path} fill={outline ? "none" : c} fillOpacity={0.4} stroke={c} strokeWidth={1}
            vectorEffect="non-scaling-stroke" fillRule="nonzero" strokeDasharray={outline ? "4 3" : undefined} />;
        })}
        {showLabels && data.labels.map((t, i) => (
          <text key={i} x={t.x} y={t.y} fill="#e6ecff" fontSize={Math.max(vb.w, vb.h) / 70} textAnchor="middle" dominantBaseline="middle"
            style={{ pointerEvents: "none" }}>{t.text}</text>
        ))}
      </svg>
      <div className="absolute top-3 right-3 flex gap-1.5">
        <Button variant="secondary" icon={ZoomIn} onClick={() => zoom(1 / 1.5)} title="Zoom in" />
        <Button variant="secondary" icon={ZoomOut} onClick={() => zoom(1.5)} title="Zoom out" />
        <Button variant="secondary" icon={Maximize2} onClick={() => setVb(full)} title="Fit" />
      </div>
      <div className="absolute bottom-3 left-3 rounded-md bg-black/50 px-2 py-1 font-mono text-[11px] text-white/80">
        {data.cell} · {data.bbox.width} × {data.bbox.height} µm · scroll to zoom, drag to pan
      </div>
    </div>
  );
}

export default function GdsViewer() {
  const [source, setSource] = useState<"example" | "upload">("example");
  const [upload, setUpload] = useState<{ name: string; data: string } | null>(null);
  const [cell, setCell] = useState("");
  const [data, setData] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showLabels, setShowLabels] = useState(true);
  const [tab, setTab] = useState("layers");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (source === "upload" && !upload) { setData(null); return; }
    let alive = true;
    setLoading(true);
    setError(null);
    const req = source === "example"
      ? getJSON<Result>(`/api/pd/gds/example?path=gds/demo_core.gds${cell ? `&cell=${encodeURIComponent(cell)}` : ""}`)
      : postJSON<Result>("/api/pd/gds", { name: upload!.name, data: upload!.data, cell: cell || null });
    req.then((r) => alive && setData(r)).catch((e) => alive && setError((e as Error).message)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [source, upload, cell]);

  const readFile = async (f: File | undefined) => {
    if (!f) return;
    setCell("");
    setHidden(new Set());
    setUpload({ name: f.name, data: toBase64(await f.arrayBuffer()) });
    setSource("upload");
  };
  const toggle = (key: string) => setHidden((h) => { const n = new Set(h); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  const totalArea = useMemo(() => (data ? data.bbox.width * data.bbox.height : 0), [data]);

  return (
    <>
      <PageHeader area="Physical design" title="GDS Viewer" icon={Shapes}
        description="Open a GDSII or OASIS layout: zoomable drawing with per-layer visibility, layer statistics (shapes and area), the cell hierarchy and how many times each cell is placed." />
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[13px] font-medium text-muted">Layout</span>
          <Segmented size="sm" value={source} onChange={(v) => { setSource(v); setCell(""); setHidden(new Set()); }} options={[
            { value: "example", label: "Example (demo_core.gds)" },
            { value: "upload", label: upload ? `Upload: ${upload.name}` : "Upload" },
          ]} />
          <Button icon={Upload} onClick={() => input.current?.click()}>Choose .gds / .oas</Button>
          <input ref={input} type="file" accept=".gds,.gds2,.oas,.oasis" className="hidden" onChange={(e) => { readFile(e.target.files?.[0]); e.target.value = ""; }} />
          {data && (
            <div className="ml-auto w-64">
              <Select value={cell || data.cell} onChange={setCell} options={data.cells.map((c) => ({ value: c, label: data.top_cells.includes(c) ? `${c} (top)` : c }))} />
            </div>
          )}
        </div>
        <p className="mt-2 text-[12.5px] text-faint">Files up to 15 MB. Layer names follow the SkyWater 130 numbering; other PDKs show layer/datatype numbers.</p>
      </Card>

      {error && <Alert tone="bad" title="Could not open the layout">{error}</Alert>}
      {source === "upload" && !upload ? <EmptyState icon={Shapes} title="No layout yet" text="Choose a .gds or .oas file from your computer." />
        : loading && !data ? <LoadingBlock label="Reading layout…" />
        : data && (
          <>
            <KpiGrid items={[
              { label: "Cell", value: data.cell, note: data.top_cells.includes(data.cell) ? "top cell" : "sub-cell", tone: "info" },
              { label: "Size", value: `${data.bbox.width} × ${data.bbox.height}`, note: `µm · ${fmtInt(Math.round(totalArea))} µm²` },
              { label: "Shapes", value: fmtInt(data.polygons), note: data.truncated ? `${fmtInt(data.shown_polygons)} largest drawn` : "all drawn" },
              { label: "Layers", value: data.layers.length },
              { label: "Placed instances", value: fmtInt(data.instances), note: `${data.cells.length} cells in the library` },
            ]} />
            {data.truncated && <Alert tone="info">Large layout: only the {fmtInt(data.shown_polygons)} biggest shapes are drawn; the statistics include every shape.</Alert>}
            <div className="mb-6 grid gap-5 xl:grid-cols-[1fr_280px]">
              <LayoutView data={data} hidden={hidden} showLabels={showLabels} />
              <Card bodyClass="p-2" title={<span className="flex items-center gap-2"><Layers className="size-4 text-brand" /> Layers</span>}
                actions={<Toggle checked={showLabels} onChange={setShowLabels} label="Labels" />}>
                <div className="max-h-[490px] overflow-y-auto">
                  {data.layers.map((l, i) => {
                    const key = `${l.layer}/${l.datatype}`;
                    const off = hidden.has(key);
                    return (
                      <button key={key} onClick={() => toggle(key)}
                        className={cx("flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left hover:bg-surface-2", off && "opacity-45")}>
                        <span className="size-3.5 shrink-0 rounded-sm border" style={{ background: COLORS[i % COLORS.length] + "99", borderColor: COLORS[i % COLORS.length] }} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">{l.name}</span>
                          <span className="block font-mono text-[11px] text-faint">{key} · {fmtInt(l.polygons)} shapes</span>
                        </span>
                        {off ? <EyeOff className="size-4 text-faint" /> : <Eye className="size-4 text-muted" />}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-1 flex gap-3 border-t border-line px-2.5 pt-2 text-[12px]">
                  <button className="font-medium text-brand hover:underline" onClick={() => setHidden(new Set())}>Show all</button>
                  <button className="font-medium text-brand hover:underline" onClick={() => setHidden(new Set(data.layers.map((l) => `${l.layer}/${l.datatype}`)))}>Hide all</button>
                </div>
              </Card>
            </div>
            <Tabs active={tab} onChange={setTab} tabs={[
              { id: "layers", label: "Layer statistics", icon: Layers, count: data.layers.length },
              { id: "tree", label: "Hierarchy", icon: Network },
              { id: "usage", label: "Cell usage", icon: Shapes, count: data.usage.length },
              { id: "labels", label: "Labels", icon: Type, count: data.labels.length },
            ]} />
            {tab === "layers" && (
              <Card bodyClass="p-4">
                <DataTable rows={data.layers} initialSort={{ key: "area", dir: "desc" }} columns={[
                  { key: "name", header: "Layer" },
                  { key: "layer", header: "GDS layer", align: "right" },
                  { key: "datatype", header: "Datatype", align: "right" },
                  { key: "polygons", header: "Shapes", align: "right", render: (l) => fmtInt(l.polygons) },
                  { key: "area", header: "Drawn area (µm²)", align: "right", render: (l) => l.area.toLocaleString("en-US", { maximumFractionDigits: 2 }) },
                  { key: "density", header: "Density", align: "right", value: (l) => l.area / (totalArea || 1),
                    render: (l) => `${((l.area / (totalArea || 1)) * 100).toFixed(1)}%` },
                ]} />
                <p className="mt-3 text-[12.5px] text-muted">Drawn area adds up shapes without merging overlaps, so density is an upper bound.</p>
              </Card>
            )}
            {tab === "tree" && <Card><Tree node={data.hierarchy} /></Card>}
            {tab === "usage" && (data.usage.length === 0 ? <Alert tone="info" title="This cell places no other cells" /> : (
              <Card bodyClass="p-4">
                <DataTable rows={data.usage} initialSort={{ key: "instances", dir: "desc" }} columns={[
                  { key: "cell", header: "Cell", mono: true },
                  { key: "instances", header: "Placements (flattened)", align: "right", render: (u) => fmtInt(u.instances) },
                ]} />
              </Card>
            ))}
            {tab === "labels" && (
              <Card bodyClass="p-4">
                <DataTable rows={data.labels} searchable columns={[
                  { key: "text", header: "Text", mono: true },
                  { key: "x", header: "x (µm)", align: "right" },
                  { key: "y", header: "y (µm)", align: "right", render: (t) => -t.y },
                  { key: "layer", header: "Layer", align: "right" },
                ]} />
              </Card>
            )}
          </>
        )}
    </>
  );
}
