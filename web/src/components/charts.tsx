// Custom SVG charts: slack histogram, digital waveform viewer, density heatmap.
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { TONE_HEX } from "../lib/format";

/** Width of a container, kept up to date on resize. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(800);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) =>
      setWidth(Math.max(320, e.contentRect.width)),
    );
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function niceTicks(min: number, max: number, count = 6) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step =
    [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-12; v += step)
    ticks.push(+v.toFixed(10));
  return ticks;
}

function Tooltip({
  x,
  y,
  children,
  width,
}: {
  x: number;
  y: number;
  children: ReactNode;
  width: number;
}) {
  const left = Math.min(Math.max(8, x + 12), width - 200);
  return (
    <div
      className="pointer-events-none absolute z-20 rounded-lg border border-line bg-surface px-3 py-2 text-[12.5px] shadow-lg"
      style={{ left, top: Math.max(0, y - 10) }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- histogram

export function SlackHistogram({
  series,
  height = 300,
}: {
  series: { name: string; color: string; values: number[] }[];
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{
    x: number;
    y: number;
    i: number;
  } | null>(null);
  const all = series.flatMap((s) => s.values);
  const pad = { l: 44, r: 16, t: 30, b: 40 };
  const lo = Math.min(0, ...all),
    hi = Math.max(0, ...all);
  const nb = 28;
  const binW = (hi - lo || 1) / nb;
  const bins = useMemo(
    () =>
      Array.from({ length: nb }, (_, i) => {
        const counts = series.map(
          (s) =>
            s.values.filter((v) => {
              const b = Math.min(nb - 1, Math.floor((v - lo) / binW));
              return b === i;
            }).length,
        );
        return { x0: lo + i * binW, x1: lo + (i + 1) * binW, counts };
      }),
    [series, lo, binW],
  );
  const ymax = Math.max(
    1,
    ...bins.map((b) => b.counts.reduce((a, c) => a + c, 0)),
  );
  const W = width - pad.l - pad.r,
    H = height - pad.t - pad.b;
  const sx = (v: number) => pad.l + ((v - lo) / (hi - lo || 1)) * W;
  const sy = (v: number) => pad.t + H - (v / ymax) * H;
  const yt = niceTicks(0, ymax, 4).filter((t) => Number.isInteger(t));

  return (
    <div ref={ref} className="relative">
      <svg
        width={width}
        height={height}
        className="block"
        onMouseLeave={() => setHover(null)}
      >
        {yt.map((t) => (
          <g key={t}>
            <line
              x1={pad.l}
              x2={width - pad.r}
              y1={sy(t)}
              y2={sy(t)}
              stroke="var(--line)"
            />
            <text
              x={pad.l - 8}
              y={sy(t) + 4}
              textAnchor="end"
              fontSize={11}
              fill="var(--faint)"
            >
              {t}
            </text>
          </g>
        ))}
        {niceTicks(lo, hi, 8).map((t) => (
          <text
            key={t}
            x={sx(t)}
            y={height - pad.b + 18}
            textAnchor="middle"
            fontSize={11}
            fill="var(--faint)"
          >
            {t}
          </text>
        ))}
        <text
          x={pad.l + W / 2}
          y={height - 4}
          textAnchor="middle"
          fontSize={12}
          fill="var(--muted)"
        >
          Slack (ns)
        </text>
        {bins.map((b, i) => {
          let acc = 0;
          return (
            <g
              key={i}
              onMouseMove={(e) =>
                setHover({
                  x: e.nativeEvent.offsetX,
                  y: e.nativeEvent.offsetY,
                  i,
                })
              }
            >
              <rect
                x={sx(b.x0)}
                y={pad.t}
                width={Math.max(1, sx(b.x1) - sx(b.x0))}
                height={H}
                fill="transparent"
              />
              {b.counts.map((c, si) => {
                if (!c) return null;
                const y0 = sy(acc + c),
                  h = sy(acc) - sy(acc + c);
                acc += c;
                return (
                  <rect
                    key={si}
                    x={sx(b.x0) + 1}
                    y={y0}
                    width={Math.max(1, sx(b.x1) - sx(b.x0) - 2)}
                    height={h}
                    rx={2}
                    fill={series[si].color}
                    opacity={hover && hover.i !== i ? 0.55 : 0.95}
                  />
                );
              })}
            </g>
          );
        })}
        <line
          x1={sx(0)}
          x2={sx(0)}
          y1={pad.t - 10}
          y2={pad.t + H}
          stroke={TONE_HEX.bad}
          strokeWidth={2}
          strokeDasharray="5 4"
        />
        <text
          x={sx(0) + 6}
          y={pad.t - 14}
          fontSize={11.5}
          fontWeight={600}
          fill={TONE_HEX.bad}
        >
          slack = 0
        </text>
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          <div className="mb-1 font-semibold tabular-nums">
            {bins[hover.i].x0.toFixed(3)} … {bins[hover.i].x1.toFixed(3)} ns
          </div>
          {series.map((s, si) => (
            <div key={s.name} className="flex items-center gap-2">
              <span
                className="size-2 rounded-sm"
                style={{ background: s.color }}
              />
              {s.name}
              <b className="ml-auto tabular-nums">{bins[hover.i].counts[si]}</b>
            </div>
          ))}
        </Tooltip>
      )}
      <div className="mt-1 flex gap-4 pl-11 text-[12.5px] text-muted">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span
              className="size-2.5 rounded-sm"
              style={{ background: s.color }}
            />
            {s.name} ({s.values.length})
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- waveforms

type Wave = { name: string; width: number; changes: [number, string][] };

/** X/Z (unknown) value? "0x5" is a hex number, not unknown. */
const isUnknown = (v: string) => !v.startsWith("0x") && /[xz]/i.test(v);

export function WaveformViewer({
  waves,
  endTime,
  timescale,
}: {
  waves: Wave[];
  endTime: number;
  timescale: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [cursor, setCursor] = useState<number | null>(null);
  const [zoom, setZoom] = useState<[number, number]>([0, endTime]);
  useEffect(() => setZoom([0, endTime]), [endTime]); // new file -> full view
  const labelW = 170,
    rowH = 38,
    top = 8,
    axisH = 28;
  const W = width - labelW - 16;
  const [t0, t1] = zoom;
  const sx = (t: number) => labelW + ((t - t0) / (t1 - t0 || 1)) * W;
  const height = top + waves.length * rowH + axisH;

  const valueAt = (w: Wave, t: number) => {
    let v = "";
    for (const [ct, cv] of w.changes) {
      if (ct <= t) v = cv;
      else break;
    }
    return v;
  };

  // zoom around the mouse with the wheel (native listener so the page does not scroll)
  const svgRef = useRef<SVGSVGElement>(null);
  const view = useRef({ t0, t1, W, endTime });
  view.current = { t0, t1, W, endTime };
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const { t0, t1, W, endTime } = view.current;
      const x = e.clientX - el.getBoundingClientRect().left;
      if (x < labelW) return;
      e.preventDefault();
      const center = t0 + ((x - labelW) / W) * (t1 - t0);
      const span = Math.min(
        endTime,
        Math.max(endTime / 500, (t1 - t0) * (e.deltaY > 0 ? 1.25 : 0.8)),
      );
      const n0 = Math.max(
        0,
        Math.min(endTime - span, center - (center - t0) * (span / (t1 - t0))),
      );
      setZoom([n0, n0 + span]);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <div ref={ref} className="relative select-none">
      <div className="mb-2 flex items-center justify-between text-[12.5px] text-faint">
        <span>Scroll on the waves to zoom · hover to read values</span>
        {(t0 > 0 || t1 < endTime) && (
          <button
            className="font-medium text-brand hover:underline"
            onClick={() => setZoom([0, endTime])}
          >
            Reset zoom
          </button>
        )}
      </div>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        className="block rounded-lg bg-surface-2"
        onMouseMove={(e) => {
          const x = e.nativeEvent.offsetX;
          setCursor(
            x >= labelW && x <= labelW + W
              ? t0 + ((x - labelW) / W) * (t1 - t0)
              : null,
          );
        }}
        onMouseLeave={() => setCursor(null)}
      >
        <defs>
          <clipPath id="wave-clip">
            <rect x={labelW} y={0} width={W} height={height} />
          </clipPath>
        </defs>
        {niceTicks(t0, t1, 10).map((t) => (
          <g key={t}>
            <line
              x1={sx(t)}
              x2={sx(t)}
              y1={top}
              y2={height - axisH}
              stroke="var(--line)"
            />
            <text
              x={sx(t)}
              y={height - 9}
              textAnchor="middle"
              fontSize={11}
              fill="var(--faint)"
            >
              {t}
            </text>
          </g>
        ))}
        <text
          x={labelW - 10}
          y={height - 9}
          textAnchor="end"
          fontSize={11}
          fill="var(--faint)"
        >
          {timescale}
        </text>
        {waves.map((w, i) => {
          const y = top + i * rowH,
            hi = y + 8,
            lo = y + rowH - 10,
            mid = (hi + lo) / 2;
          const segs = w.changes
            .map(([t, v], k) => ({
              t,
              v,
              end: k + 1 < w.changes.length ? w.changes[k + 1][0] : endTime,
            }))
            .filter((s) => s.end >= t0 && s.t <= t1);
          return (
            <g key={w.name}>
              <text
                x={labelW - 10}
                y={mid + 4}
                textAnchor="end"
                fontSize={12}
                fontFamily="var(--font-mono)"
                fill="var(--text)"
              >
                {w.name.length > 22 ? "…" + w.name.slice(-21) : w.name}
              </text>
              {w.width > 1 && (
                <text
                  x={labelW - 10}
                  y={mid + 16}
                  textAnchor="end"
                  fontSize={9.5}
                  fill="var(--faint)"
                >
                  [{w.width}]
                </text>
              )}
              <g clipPath="url(#wave-clip)">
                {segs.map((s, k) => {
                  const x0 = sx(Math.max(s.t, t0)),
                    x1 = sx(Math.min(s.end, t1));
                  const unknown = isUnknown(s.v);
                  if (w.width === 1 && !unknown) {
                    const yv = s.v === "1" ? hi : lo;
                    const prev = segs[k - 1];
                    const prevY =
                      prev && !isUnknown(prev.v)
                        ? prev.v === "1"
                          ? hi
                          : lo
                        : yv;
                    return (
                      <g key={k}>
                        {k > 0 && s.t >= t0 && (
                          <line
                            x1={x0}
                            x2={x0}
                            y1={prevY}
                            y2={yv}
                            stroke={TONE_HEX.good}
                            strokeWidth={1.6}
                          />
                        )}
                        <line
                          x1={x0}
                          x2={x1}
                          y1={yv}
                          y2={yv}
                          stroke={TONE_HEX.good}
                          strokeWidth={1.6}
                        />
                      </g>
                    );
                  }
                  const color = unknown ? TONE_HEX.bad : TONE_HEX.good;
                  const slant = Math.min(4, (x1 - x0) / 3);
                  return (
                    <g key={k}>
                      <path
                        d={`M${x0},${mid} L${x0 + slant},${hi} L${x1 - slant},${hi} L${x1},${mid} L${x1 - slant},${lo} L${x0 + slant},${lo} Z`}
                        fill={color}
                        fillOpacity={unknown ? 0.18 : 0.12}
                        stroke={color}
                        strokeWidth={1.2}
                      />
                      {x1 - x0 > 34 && (
                        <text
                          x={(x0 + x1) / 2}
                          y={mid + 4}
                          textAnchor="middle"
                          fontSize={11}
                          fontFamily="var(--font-mono)"
                          fill="var(--text)"
                        >
                          {s.v.length > Math.floor((x1 - x0) / 7)
                            ? s.v.slice(
                                0,
                                Math.max(1, Math.floor((x1 - x0) / 7) - 1),
                              ) + "…"
                            : s.v}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
              <line
                x1={labelW}
                x2={labelW + W}
                y1={y + rowH}
                y2={y + rowH}
                stroke="var(--line)"
                strokeOpacity={0.5}
              />
            </g>
          );
        })}
        {cursor != null && (
          <g>
            <line
              x1={sx(cursor)}
              x2={sx(cursor)}
              y1={top}
              y2={height - axisH}
              stroke="var(--brand)"
              strokeWidth={1}
            />
            <rect
              x={sx(cursor) - 28}
              y={height - axisH + 2}
              width={56}
              height={16}
              rx={4}
              fill="var(--brand)"
            />
            <text
              x={sx(cursor)}
              y={height - axisH + 14}
              textAnchor="middle"
              fontSize={11}
              fill="#fff"
            >
              {cursor.toFixed(0)}
            </text>
            {waves.map((w, i) => (
              <text
                key={w.name}
                x={Math.min(sx(cursor) + 6, labelW + W - 60)}
                y={top + i * rowH + 12}
                fontSize={11}
                fontWeight={600}
                fontFamily="var(--font-mono)"
                fill="var(--brand)"
              >
                {valueAt(w, cursor)}
              </text>
            ))}
          </g>
        )}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------- heatmap

export function DensityHeatmap({
  grid,
  macroBins,
  label,
}: {
  grid: number[][];
  macroBins: [number, number][];
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{
    x: number;
    y: number;
    v: number;
    macro: boolean;
  } | null>(null);
  const rows = grid.length,
    cols = grid[0]?.length ?? 1;
  const cell = width / cols;
  const height = cell * rows;
  const peak = Math.max(1e-9, ...grid.flat());
  const macros = useMemo(
    () => new Set(macroBins.map(([x, y]) => `${x},${y}`)),
    [macroBins],
  );
  const color = (v: number) => {
    if (v <= 0) return "var(--surface-3)";
    const t = Math.sqrt(v / peak); // perceptual boost for sparse areas
    const stops = [
      [255, 237, 160],
      [254, 178, 76],
      [240, 59, 32],
      [150, 10, 40],
    ];
    const p = t * (stops.length - 1),
      i = Math.min(stops.length - 2, Math.floor(p)),
      f = p - i;
    const c = stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f));
    return `rgb(${c.join(",")})`;
  };
  return (
    <div ref={ref} className="relative">
      <svg
        width={width}
        height={height}
        className="block overflow-hidden rounded-lg"
        onMouseLeave={() => setHover(null)}
      >
        {grid.map((row, gy) =>
          row.map((v, gx) => {
            const macro = macros.has(`${gx},${gy}`);
            return (
              <rect
                key={`${gx}-${gy}`}
                x={gx * cell}
                y={(rows - 1 - gy) * cell}
                width={cell + 0.5}
                height={cell + 0.5}
                fill={macro ? "#7b869c" : color(v)}
                onMouseMove={(e) =>
                  setHover({
                    x: e.nativeEvent.offsetX,
                    y: e.nativeEvent.offsetY,
                    v,
                    macro,
                  })
                }
              />
            );
          }),
        )}
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          {hover.macro ? (
            <b>Macro</b>
          ) : (
            <span>
              {label}: <b className="tabular-nums">{hover.v.toFixed(1)}</b>
            </span>
          )}
        </Tooltip>
      )}
      <div className="mt-3 flex items-center gap-3 text-[12px] text-muted">
        <span>sparse</span>
        <span
          className="h-2 w-40 rounded-full"
          style={{
            background:
              "linear-gradient(90deg, rgb(255,237,160), rgb(254,178,76), rgb(240,59,32), rgb(150,10,40))",
          }}
        />
        <span>dense</span>
        <span className="ml-4 inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-[#7b869c]" />
          macro
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- AXI timeline

export type TimelineTxn = {
  kind: string;
  id: number | null;
  addr: string;
  length: number;
  status: string;
  start_cycle: number;
  end_cycle: number | null;
  request_cycle?: number;
  waited?: number;
};
export type TimelineMark = {
  cycle: number;
  rule: string;
  severity: string;
  message: string;
};

const STATUS_COLOR: Record<string, string> = {
  OKAY: TONE_HEX.good,
  EXOKAY: TONE_HEX.good,
  SLVERR: TONE_HEX.bad,
  DECERR: TONE_HEX.bad,
  NO_RESPONSE: TONE_HEX.warn,
};

/** Gantt-style view: one bar per transaction from request handshake to final response. */
export function AxiTimeline({
  txns,
  marks,
  cycles,
  onSelect,
}: {
  txns: TimelineTxn[];
  marks: TimelineMark[];
  cycles: number;
  onSelect?: (i: number) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{
    x: number;
    y: number;
    text: ReactNode;
  } | null>(null);
  const labelW = 190,
    rowH = 26,
    top = 34,
    axisH = 26;
  const W = width - labelW - 12;
  const sx = (c: number) => labelW + (c / Math.max(1, cycles)) * W;
  const height = top + txns.length * rowH + axisH;
  return (
    <div ref={ref} className="relative">
      <svg
        width={width}
        height={height}
        className="block rounded-lg bg-surface-2"
        onMouseLeave={() => setHover(null)}
      >
        {niceTicks(0, cycles, 10).map((t) => (
          <g key={t}>
            <line
              x1={sx(t)}
              x2={sx(t)}
              y1={top - 6}
              y2={height - axisH}
              stroke="var(--line)"
            />
            <text
              x={sx(t)}
              y={height - 9}
              textAnchor="middle"
              fontSize={11}
              fill="var(--faint)"
            >
              {t}
            </text>
          </g>
        ))}
        <text
          x={labelW - 10}
          y={height - 9}
          textAnchor="end"
          fontSize={11}
          fill="var(--faint)"
        >
          clock cycle
        </text>
        <text
          x={labelW - 10}
          y={18}
          textAnchor="end"
          fontSize={11}
          fill="var(--faint)"
        >
          violations
        </text>
        {marks.map((m, i) => (
          <g
            key={i}
            onMouseMove={(e) =>
              setHover({
                x: e.nativeEvent.offsetX,
                y: e.nativeEvent.offsetY,
                text: (
                  <>
                    <b
                      className={
                        m.severity === "ERROR" ? "text-bad" : "text-warn"
                      }
                    >
                      {m.rule}
                    </b>{" "}
                    · cycle {m.cycle}
                    <div className="max-w-xs text-muted">{m.message}</div>
                  </>
                ),
              })
            }
          >
            <line
              x1={sx(m.cycle)}
              x2={sx(m.cycle)}
              y1={22}
              y2={height - axisH}
              stroke={m.severity === "ERROR" ? TONE_HEX.bad : TONE_HEX.warn}
              strokeOpacity={0.35}
              strokeDasharray="3 3"
            />
            <path
              d={`M${sx(m.cycle)},24 l-6,-10 h12 z`}
              fill={m.severity === "ERROR" ? TONE_HEX.bad : TONE_HEX.warn}
            />
          </g>
        ))}
        {txns.map((t, i) => {
          const y = top + i * rowH;
          const end = t.end_cycle ?? cycles;
          const color = STATUS_COLOR[t.status] ?? TONE_HEX.info;
          const x0 = sx(t.start_cycle),
            x1 = Math.max(x0 + 4, sx(end));
          return (
            <g
              key={i}
              className={onSelect ? "cursor-pointer" : ""}
              onClick={() => onSelect?.(i)}
              onMouseMove={(e) =>
                setHover({
                  x: e.nativeEvent.offsetX,
                  y: e.nativeEvent.offsetY,
                  text: (
                    <>
                      <b>
                        {t.kind} {t.addr}
                      </b>{" "}
                      · {t.length} beat{t.length > 1 ? "s" : ""}
                      <div className="text-muted">
                        cycles {t.start_cycle} → {t.end_cycle ?? "never"} ·{" "}
                        {t.status}
                        {t.waited
                          ? ` · waited ${t.waited} cycles for READY`
                          : ""}
                      </div>
                    </>
                  ),
                })
              }
            >
              <rect
                x={0}
                y={y}
                width={width}
                height={rowH}
                fill="transparent"
              />
              <text
                x={labelW - 10}
                y={y + rowH / 2 + 4}
                textAnchor="end"
                fontSize={11.5}
                fontFamily="var(--font-mono)"
                fill="var(--text)"
              >
                <tspan
                  fill={t.kind === "WRITE" ? "#3b74e6" : "#7c4fd6"}
                  fontWeight={700}
                >
                  {t.kind === "WRITE" ? "W" : "R"}
                </tspan>
                {` ${t.addr}`}
                {t.id != null ? ` #${t.id}` : ""}
              </text>
              {t.waited ? (
                <rect
                  x={sx(t.request_cycle ?? t.start_cycle)}
                  y={y + 9}
                  width={Math.max(2, x0 - sx(t.request_cycle ?? t.start_cycle))}
                  height={rowH - 18}
                  rx={2}
                  fill={TONE_HEX.warn}
                  fillOpacity={0.45}
                />
              ) : null}
              <rect
                x={x0}
                y={y + 5}
                width={x1 - x0}
                height={rowH - 10}
                rx={4}
                fill={color}
                fillOpacity={t.end_cycle == null ? 0.25 : 0.85}
                stroke={color}
                strokeDasharray={t.end_cycle == null ? "4 3" : undefined}
              />
              {x1 - x0 > 40 && (
                <text
                  x={x0 + 6}
                  y={y + rowH / 2 + 4}
                  fontSize={10.5}
                  fill={t.end_cycle == null ? "var(--text)" : "#fff"}
                  fontWeight={600}
                >
                  {t.end_cycle == null
                    ? "no response"
                    : `${end - t.start_cycle} cyc`}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y} width={width}>
          {hover.text}
        </Tooltip>
      )}
    </div>
  );
}
