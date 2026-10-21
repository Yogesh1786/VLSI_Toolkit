import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CircleAlert, Clock, Database, Gauge, History, MessageSquareText, Star } from "lucide-react";
import { getJSON } from "../lib/api";
import { DataTable } from "../components/DataTable";
import { Alert, Badge, BarList, Card, EmptyState, KpiGrid, LoadingBlock, PageHeader, Segmented, StatusBadge, Tabs } from "../components/ui";
import { fmtInt } from "../lib/format";

type FileRef = { name: string; bytes: number };
type Event = {
  id?: string; ts: number; tool: string; endpoint: string; ok: boolean; status: number; ms: number;
  files: FileRef[]; result: Record<string, unknown>; error: string | null;
};
type DbInfo = { kind: "mongodb" | "sqlite"; connected: boolean; location?: string; error?: string | null; warning?: string };
type ActivityData = {
  days: number;
  totals: { runs: number; failures: number; success_rate: number | null; avg_ms: number | null; files: number; bytes: number;
    tools_used: number; all_time_runs: number; last_run: number | null };
  by_tool: { tool: string; runs: number; failures: number; avg_ms: number }[];
  by_day: { day: string; runs: number; failures: number }[];
  feedback: { count: number; avg_rating: number | null };
  details: boolean;
  database: DbInfo;
  recent?: Event[];
  failures?: Event[];
};
type Feedback = { id: string; ts: number; message: string; rating: number | null; name: string; email: string; page: string };

const when = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const dayLabel = (d: string) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
const size = (b: number) => (b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`);
const ms = (v: number | null) => (v == null ? "–" : v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(2)} s`);

/** "issues 3 · clocks 2" from the stored result counts. */
function resultText(r: Record<string, unknown>) {
  const counts = r.counts as Record<string, number> | undefined;
  const parts = counts ? Object.entries(counts).filter(([, v]) => v).map(([k, v]) => `${v} ${k.toLowerCase()}`) : [];
  for (const [k, v] of Object.entries(r)) {
    if (k !== "counts" && typeof v === "number" && parts.length < 4) parts.push(`${k.replace(/_/g, " ")} ${v}`);
  }
  return parts.join(" · ") || "–";
}

function EventTable({ rows }: { rows: Event[] }) {
  return (
    <DataTable rows={rows} searchable initialSort={{ key: "ts", dir: "desc" }} columns={[
      { key: "ts", header: "When", render: (e) => <span className="whitespace-nowrap">{when(e.ts)}</span> },
      { key: "ok", header: "Status", value: (e) => (e.ok ? 1 : 0), render: (e) => <StatusBadge status={e.ok ? "PASS" : "FAIL"} /> },
      { key: "tool", header: "Tool" },
      { key: "files", header: "Files", wrap: true, value: (e) => e.files.map((f) => f.name).join(" "),
        render: (e) => e.files.length ? <span className="font-mono text-[12px]">{e.files.slice(0, 3).map((f) => `${f.name} (${size(f.bytes)})`).join(", ")}{e.files.length > 3 ? ` +${e.files.length - 3}` : ""}</span> : "–" },
      { key: "result", header: "Result / error", wrap: true, value: (e) => e.error ?? "",
        render: (e) => e.error ? <span className="text-bad">{e.error}</span> : <span className="text-muted">{resultText(e.result)}</span> },
      { key: "ms", header: "Time", align: "right", render: (e) => ms(e.ms) },
    ]} />
  );
}

export default function Activity() {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const [data, setData] = useState<ActivityData | null>(null);
  const [feedback, setFeedback] = useState<Feedback[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("recent");

  useEffect(() => {
    let alive = true;
    getJSON<ActivityData>(`/api/activity?days=${days}`)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError((e as Error).message));
    return () => { alive = false; };
  }, [days]);

  useEffect(() => {
    if (!data?.details) return;
    getJSON<{ feedback: Feedback[] }>("/api/feedback").then((r) => setFeedback(r.feedback)).catch(() => setFeedback([]));
  }, [data?.details]);

  const t = data?.totals;
  const db = data?.database;

  return (
    <>
      <PageHeader area="Tracking" title="Activity" icon={Gauge}
        description="How the toolkit is used: tool runs per day, the most-used tools, failures and visitor feedback. Only file names, sizes and result counts are recorded, never file contents."
        actions={<Segmented value={days} onChange={setDays} options={[
          { value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />} />

      {db && (
        <div className="mb-5 flex flex-wrap items-center gap-2 text-[13px] text-muted">
          <Database className="size-4" />
          Stored in <b className="text-fg">{db.kind === "mongodb" ? "MongoDB" : "local SQLite"}</b>
          {db.location && <span className="font-mono text-[12px] text-faint">{db.location}</span>}
          <Badge tone={db.connected ? "good" : "bad"}>{db.connected ? "connected" : "not reachable"}</Badge>
        </div>
      )}
      {db?.warning && <div className="mb-5"><Alert tone="warn" title="MongoDB not used">{db.warning}</Alert></div>}
      {db && !db.connected && db.error && <div className="mb-5"><Alert tone="bad" title="Database error">{db.error}</Alert></div>}
      {error && <Alert tone="bad" title="Could not load activity">{error}</Alert>}

      {!data ? (!error && <LoadingBlock label="Loading activity…" />) : (
        <>
          <KpiGrid items={[
            { label: "Tool runs", value: fmtInt(t!.runs), note: `last ${data.days} days · ${fmtInt(t!.all_time_runs)} all time`, tone: "info" },
            { label: "Success rate", value: t!.success_rate == null ? "–" : `${(t!.success_rate * 100).toFixed(1)}%`,
              note: t!.failures ? `${t!.failures} failed` : "no failures", tone: t!.failures ? "warn" : "good",
              hint: "A failed run is a file the tool could not read, or a server error." },
            { label: "Avg. analysis time", value: ms(t!.avg_ms), note: `${t!.tools_used} tools used` },
            { label: "Files analyzed", value: fmtInt(t!.files), note: size(t!.bytes) },
            { label: "Feedback", value: fmtInt(data.feedback.count),
              note: data.feedback.avg_rating != null ? <span className="inline-flex items-center gap-1"><Star className="size-3 fill-amber-400 text-amber-400" />{data.feedback.avg_rating} average</span> : "no ratings yet" },
          ]} />

          {t!.runs === 0 ? (
            <EmptyState icon={History} title="No tool runs in this period" text="Every analysis you run on any tool page is counted here. Open a tool and try one of its examples." />
          ) : (
            <div className="mb-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
              <Card title="Runs per day" subtitle="Successful and failed tool runs">
                <div className="h-72 [--chart-fail:#e5484d] [--chart-ok:#2f5bd3] dark:[--chart-ok:#5f83ef]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.by_day.map((d) => ({ ...d, ok: d.runs - d.failures }))} barCategoryGap="22%">
                      <CartesianGrid vertical={false} stroke="var(--line)" strokeOpacity={0.6} />
                      <XAxis dataKey="day" tickFormatter={dayLabel} tick={{ fontSize: 11, fill: "var(--faint)" }} axisLine={false} tickLine={false}
                        interval="preserveStartEnd" minTickGap={24} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--faint)" }} axisLine={false} tickLine={false} width={32} />
                      <Tooltip cursor={{ fill: "var(--surface-3)", opacity: 0.6 }} labelFormatter={(d) => dayLabel(String(d))}
                        contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12, color: "var(--text)" }} />
                      <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "var(--muted)" }} />
                      <Bar dataKey="ok" name="Successful" stackId="r" fill="var(--chart-ok)" stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
                      <Bar dataKey="failures" name="Failed" stackId="r" fill="var(--chart-fail)" stroke="var(--surface)" strokeWidth={1} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
              <Card title="Most used tools" subtitle={`Runs in the last ${data.days} days`}>
                <BarList items={data.by_tool.slice(0, 10).map((x) => ({ label: x.failures ? `${x.tool} (${x.failures} failed)` : x.tool, value: x.runs }))} />
              </Card>
            </div>
          )}

          {data.details ? (
            <>
              <Tabs active={tab} onChange={setTab} tabs={[
                { id: "recent", label: "Recent runs", icon: Clock, count: data.recent?.length ?? 0 },
                { id: "failures", label: "Failures", icon: CircleAlert, count: data.failures?.length ?? 0 },
                { id: "feedback", label: "Feedback", icon: MessageSquareText, count: feedback?.length ?? data.feedback.count },
              ]} />
              {tab === "recent" && (data.recent?.length ? <Card bodyClass="p-4"><EventTable rows={data.recent} /></Card>
                : <Alert tone="info" title="No runs recorded yet" />)}
              {tab === "failures" && (data.failures?.length ? <Card bodyClass="p-4"><EventTable rows={data.failures} /></Card>
                : <Alert tone="good" title="No failed runs" />)}
              {tab === "feedback" && (!feedback ? <LoadingBlock /> : feedback.length === 0
                ? <Alert tone="info" title="No feedback yet">Visitors can send it with the Feedback button at the top of every page.</Alert>
                : (
                  <div className="space-y-3">
                    {feedback.map((f) => (
                      <Card key={f.id} bodyClass="p-4">
                        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-muted">
                          {f.rating != null && (
                            <span className="inline-flex" aria-label={`${f.rating} of 5 stars`}>
                              {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={`size-3.5 ${n <= f.rating! ? "fill-amber-400 text-amber-400" : "text-line-strong"}`} />)}
                            </span>
                          )}
                          <b className="text-fg">{f.name || "Anonymous"}</b>
                          {f.email && <a href={`mailto:${f.email}`} className="text-brand hover:underline">{f.email}</a>}
                          {f.page && <span className="font-mono text-[11.5px]">{f.page}</span>}
                          <span className="ml-auto">{when(f.ts)}</span>
                        </div>
                        <p className="whitespace-pre-wrap text-[13.5px]">{f.message}</p>
                      </Card>
                    ))}
                  </div>
                ))}
            </>
          ) : (
            <Alert tone="info" title="Totals only">File names, error messages and feedback messages are private: they are shown in the local app, which reads the same database.</Alert>
          )}
        </>
      )}
    </>
  );
}
