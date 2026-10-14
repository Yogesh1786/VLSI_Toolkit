// Draws a state machine: states on a circle (reset state on top), arrows with conditions.
import { useMemo, useState } from "react";
import { TONE_HEX } from "../lib/format";

export type FsmData = {
  states: string[];
  reset_state: string | null;
  unreachable: string[];
  dead_ends: string[];
  transitions: { src: string; dst: string; condition: string }[];
};

const W = 760,
  H = 540,
  R_NODE = 40;

export function StateDiagram({ fsm }: { fsm: FsmData }) {
  const [hover, setHover] = useState<string | null>(null);
  const order = useMemo(() => {
    const s = [...fsm.states];
    if (fsm.reset_state) {
      s.splice(s.indexOf(fsm.reset_state), 1);
      s.unshift(fsm.reset_state);
    }
    return s;
  }, [fsm]);
  const pos = useMemo(() => {
    const n = order.length,
      rx = W / 2 - 110,
      ry = H / 2 - 80;
    return Object.fromEntries(
      order.map((s, i) => {
        const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
        return [
          s,
          { x: W / 2 + rx * Math.cos(a), y: H / 2 + ry * Math.sin(a) },
        ];
      }),
    );
  }, [order]);

  // merge transitions with the same src/dst so conditions stack on one arrow
  const edges = useMemo(() => {
    const m = new Map<string, { src: string; dst: string; conds: string[] }>();
    fsm.transitions.forEach((t) => {
      const k = `${t.src}->${t.dst}`;
      const e = m.get(k) ?? { src: t.src, dst: t.dst, conds: [] };
      e.conds.push(t.condition);
      m.set(k, e);
    });
    return [...m.values()];
  }, [fsm]);
  const pairs = new Set(edges.map((e) => `${e.src}->${e.dst}`));

  const short = (c: string) => (c.length > 26 ? c.slice(0, 24) + "…" : c);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="block h-auto w-full rounded-lg bg-surface-2"
      role="img"
      aria-label="State diagram"
    >
      <defs>
        {["normal", "hi"].map((k) => (
          <marker
            key={k}
            id={`arrow-${k}`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path
              d="M0,0 L10,5 L0,10 z"
              fill={k === "hi" ? "var(--brand)" : "var(--faint)"}
            />
          </marker>
        ))}
      </defs>
      {edges.map((e) => {
        const a = pos[e.src],
          b = pos[e.dst];
        if (!a || !b) return null;
        const active = hover === e.src || hover === e.dst;
        const stroke = active ? "var(--brand)" : "var(--faint)";
        const label = e.conds.map(short).join("  |  ");
        if (e.src === e.dst) {
          // self loop above the node, pointing away from the centre
          const ang = Math.atan2(a.y - H / 2, a.x - W / 2);
          const cx = a.x + Math.cos(ang) * (R_NODE + 22),
            cy = a.y + Math.sin(ang) * (R_NODE + 22);
          return (
            <g key={`${e.src}-self`}>
              <circle
                cx={cx}
                cy={cy}
                r={18}
                fill="none"
                stroke={stroke}
                strokeWidth={1.5}
              />
              <text
                x={cx + Math.cos(ang) * 28}
                y={cy + Math.sin(ang) * 28 + 4}
                textAnchor="middle"
                fontSize={11}
                fill={active ? "var(--brand)" : "var(--muted)"}
              >
                {label}
              </text>
            </g>
          );
        }
        const dx = b.x - a.x,
          dy = b.y - a.y,
          len = Math.hypot(dx, dy) || 1;
        const ux = dx / len,
          uy = dy / len;
        const bend = pairs.has(`${e.dst}->${e.src}`) ? 34 : 14; // curve apart when both directions exist
        const sx = a.x + ux * R_NODE,
          sy = a.y + uy * R_NODE,
          tx = b.x - ux * (R_NODE + 3),
          ty = b.y - uy * (R_NODE + 3);
        const mx = (sx + tx) / 2 - uy * bend,
          my = (sy + ty) / 2 + ux * bend;
        return (
          <g key={`${e.src}-${e.dst}`}>
            <path
              d={`M${sx},${sy} Q${mx},${my} ${tx},${ty}`}
              fill="none"
              stroke={stroke}
              strokeWidth={active ? 2 : 1.5}
              markerEnd={`url(#arrow-${active ? "hi" : "normal"})`}
            />
            <text
              x={mx}
              y={my - 6}
              textAnchor="middle"
              fontSize={11}
              fontFamily="var(--font-mono)"
              fill={active ? "var(--brand)" : "var(--muted)"}
              paintOrder="stroke"
              stroke="var(--surface-2)"
              strokeWidth={4}
            >
              {label}
            </text>
          </g>
        );
      })}
      {order.map((s) => {
        const p = pos[s];
        const unreachable = fsm.unreachable.includes(s),
          dead = fsm.dead_ends.includes(s),
          reset = s === fsm.reset_state;
        const color = unreachable
          ? TONE_HEX.bad
          : dead
            ? TONE_HEX.warn
            : reset
              ? "var(--brand)"
              : "var(--line-strong)";
        return (
          <g
            key={s}
            onMouseEnter={() => setHover(s)}
            onMouseLeave={() => setHover(null)}
            className="cursor-default"
          >
            {reset && (
              <circle
                cx={p.x}
                cy={p.y}
                r={R_NODE + 5}
                fill="none"
                stroke="var(--brand)"
                strokeWidth={1.5}
              />
            )}
            <circle
              cx={p.x}
              cy={p.y}
              r={R_NODE}
              fill="var(--surface)"
              stroke={color}
              strokeWidth={hover === s ? 3 : 2}
              strokeDasharray={unreachable ? "5 4" : undefined}
            />
            <text
              x={p.x}
              y={p.y + 4}
              textAnchor="middle"
              fontSize={s.length > 9 ? 10.5 : 12.5}
              fontWeight={600}
              fontFamily="var(--font-mono)"
              fill="var(--text)"
            >
              {s.length > 13 ? s.slice(0, 12) + "…" : s}
            </text>
          </g>
        );
      })}
      {fsm.reset_state &&
        (() => {
          const p = pos[fsm.reset_state];
          return (
            <g>
              <line
                x1={p.x - 90}
                y1={p.y}
                x2={p.x - R_NODE - 7}
                y2={p.y}
                stroke="var(--brand)"
                strokeWidth={1.5}
                markerEnd="url(#arrow-hi)"
              />
              <text x={p.x - 92} y={p.y - 6} fontSize={11} fill="var(--brand)">
                reset
              </text>
            </g>
          );
        })()}
    </svg>
  );
}
