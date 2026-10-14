// Small helpers for numbers, files and status colors.

export type Tone = "good" | "bad" | "warn" | "info" | "neutral";

export const STATUS_TONE: Record<string, Tone> = {
  PASS: "good",
  MET: "good",
  OK: "good",
  FAIL: "bad",
  ERROR: "bad",
  VIOLATED: "bad",
  INCOMPLETE: "warn",
  WARNING: "warn",
  INFO: "info",
};

export const TONE_HEX: Record<Tone, string> = {
  good: "#1f9d55",
  bad: "#e5484d",
  warn: "#e08a00",
  info: "#3b74e6",
  neutral: "#8792a8",
};

export const PALETTE = [
  "#3b74e6",
  "#e08a00",
  "#1f9d55",
  "#c2417a",
  "#7c4fd6",
  "#1aa3a3",
];

/** 1.23e-11 -> "12.3 p" + unit */
export function eng(value: number | null | undefined, unit = ""): string {
  if (value == null || Number.isNaN(value)) return "–";
  const steps: [number, string][] = [
    [1e9, "G"],
    [1e6, "M"],
    [1e3, "k"],
    [1, ""],
    [1e-3, "m"],
    [1e-6, "µ"],
    [1e-9, "n"],
    [1e-12, "p"],
    [1e-15, "f"],
  ];
  for (const [exp, prefix] of steps) {
    if (Math.abs(value) >= exp)
      return `${+(value / exp).toPrecision(4)} ${prefix}${unit}`;
  }
  return `${+value.toPrecision(3)} ${unit}`;
}

export const fmtInt = (n: number) => n.toLocaleString("en-US");
export const pct = (x: number, digits = 1) => `${(x * 100).toFixed(digits)}%`;

export function downloadText(name: string, text: string, mime = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function toCSV(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [
    cols.join(","),
    ...rows.map((r) => cols.map((c) => esc(r[c])).join(",")),
  ].join("\n");
}

/** Download several text files as separate downloads (no zip library needed). */
export function downloadAll(files: Record<string, string>) {
  Object.entries(files).forEach(([name, text], i) =>
    setTimeout(() => downloadText(name, text), i * 250),
  );
}

export const cx = (...c: (string | false | null | undefined)[]) =>
  c.filter(Boolean).join(" ");
