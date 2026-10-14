import { useEffect, useMemo, useState } from "react";
import {
  Boxes,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  GitFork,
  Network,
  Workflow,
} from "lucide-react";
import { getJSON, useAnalysis, type SourceFile } from "../lib/api";
import { FileSource } from "../components/FileSource";
import { DataTable } from "../components/DataTable";
import { StateDiagram, type FsmData } from "../components/StateDiagram";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  KpiGrid,
  LoadingBlock,
  PageHeader,
  Select,
  Tabs,
} from "../components/ui";
import { cx } from "../lib/format";

type Node = {
  module: string;
  instance: string;
  defined: boolean;
  file: string | null;
  fsm_count: number;
  children: Node[];
  params?: Record<string, string>;
  recursive?: boolean;
};
type Fsm = FsmData & {
  module: string;
  state_var: string;
  line: number;
  file: string;
};
type Result = {
  tops: string[];
  main_top: string | null;
  unused: string[];
  trees: Node[];
  total_instances: number;
  undefined: string[];
  duplicates: string[];
  fsms: Fsm[];
  modules: {
    name: string;
    file: string;
    line: number;
    instances: number;
    used: number;
    fsms: number;
    children: string[];
  }[];
};

function TreeNode({
  node,
  depth,
  root,
}: {
  node: Node;
  depth: number;
  root?: boolean;
}) {
  const [open, setOpen] = useState(depth < 3);
  const has = node.children.length > 0;
  const params = node.params ? Object.entries(node.params) : [];
  return (
    <div>
      <div
        className={cx(
          "group flex items-center gap-2 rounded-md py-1.5 pr-2 hover:bg-surface-2",
          !node.defined && "text-bad",
        )}
        style={{ paddingLeft: depth * 22 + 6 }}
      >
        <button
          onClick={() => setOpen(!open)}
          className={cx(
            "grid size-5 place-items-center rounded text-faint hover:bg-surface-3",
            !has && "invisible",
          )}
        >
          {open ? (
            <ChevronDown className="size-4" />
          ) : (
            <ChevronRight className="size-4" />
          )}
        </button>
        <Boxes
          className={cx(
            "size-4 shrink-0",
            node.defined ? "text-brand" : "text-bad",
          )}
        />
        {root ? (
          <span className="font-mono text-[13.5px] font-semibold">
            {node.module}
          </span>
        ) : (
          <span className="font-mono text-[13px]">
            <span className="font-semibold">{node.instance}</span>
            <span className="text-muted"> : {node.module}</span>
          </span>
        )}
        {params.length > 0 && (
          <span className="truncate font-mono text-[11.5px] text-faint">
            #({params.map(([k, v]) => `${k}=${v}`).join(", ")})
          </span>
        )}
        {node.fsm_count > 0 && (
          <Badge tone="info">
            <Workflow className="size-3" />
            {node.fsm_count} FSM
          </Badge>
        )}
        {!node.defined && (
          <Badge tone="bad">
            <CircleHelp className="size-3" />
            not defined
          </Badge>
        )}
        {node.recursive && <Badge tone="warn">recursive</Badge>}
        {has && (
          <span className="ml-auto text-[12px] text-faint opacity-0 group-hover:opacity-100">
            {node.children.length} children
          </span>
        )}
      </div>
      {open &&
        node.children.map((c, i) => (
          <TreeNode key={`${c.instance}-${i}`} node={c} depth={depth + 1} />
        ))}
    </div>
  );
}

export default function Hierarchy() {
  const [examples, setExamples] = useState<string[]>([]);
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [tab, setTab] = useState("tree");
  const [fsmKey, setFsmKey] = useState("");
  useEffect(() => {
    getJSON<string[]>("/api/examples?folder=rtl_project")
      .then(setExamples)
      .catch(() => setExamples([]));
  }, []);
  const { data, loading, error } = useAnalysis<Result>(
    "/api/rtl/hierarchy",
    files ? { files } : null,
  );
  const fsms = data?.fsms ?? [];
  const fsm =
    fsms.find((f) => `${f.module}.${f.state_var}` === fsmKey) ?? fsms[0];
  const issues = useMemo(
    () =>
      data
        ? data.undefined.length +
          data.unused.length +
          fsms.reduce(
            (s, f) => s + f.unreachable.length + f.dead_ends.length,
            0,
          )
        : 0,
    [data, fsms],
  );

  return (
    <>
      <PageHeader
        area="RTL design"
        title="Hierarchy & FSM Viewer"
        icon={Network}
        description="Upload a whole RTL project: see the instance tree, black boxes and unused modules, and automatically drawn state diagrams for every state machine."
      />
      <Card className="mb-6">
        {examples.length > 0 && (
          <FileSource
            label="RTL project files"
            multiple
            examples={examples}
            accept=".v,.sv,.vh,.svh"
            onChange={setFiles}
          />
        )}
      </Card>

      {error && (
        <Alert tone="bad" title="Request failed">
          {error}
        </Alert>
      )}
      {!files ? (
        <EmptyState
          icon={Network}
          title="No files yet"
          text="Upload all the Verilog/SystemVerilog files of a design (you can select many at once)."
        />
      ) : loading && !data ? (
        <LoadingBlock />
      ) : (
        data && (
          <>
            <KpiGrid
              items={[
                {
                  label: "Top module",
                  value: data.main_top ?? "–",
                  note: data.unused.length
                    ? `+ ${data.unused.length} unused module${data.unused.length > 1 ? "s" : ""}`
                    : "single top",
                  tone: data.unused.length ? "warn" : "good",
                },
                {
                  label: "Modules",
                  value: data.modules.length,
                  note: `${files.length} files`,
                },
                { label: "Instances", value: data.total_instances },
                {
                  label: "State machines",
                  value: fsms.length,
                  tone: "info",
                  note:
                    fsms
                      .map((f) => f.module)
                      .slice(0, 2)
                      .join(", ") || undefined,
                },
                {
                  label: "Findings",
                  value: issues,
                  tone: issues ? "warn" : "good",
                  note: issues ? "see below" : "clean",
                },
              ]}
            />
            {data.undefined.length > 0 && (
              <Alert tone="warn" title="Instantiated but not defined">
                {data.undefined.join(", ")}: black boxes, library cells or
                missing files.
              </Alert>
            )}
            {data.unused.length > 0 && (
              <Alert tone="info" title="Defined but never instantiated">
                {data.unused.join(", ")}: leftovers, or tops of other designs.
              </Alert>
            )}
            {data.duplicates.length > 0 && (
              <Alert tone="bad" title="Defined more than once">
                {data.duplicates.join(", ")}
              </Alert>
            )}
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { id: "tree", label: "Instance tree", icon: GitFork },
                {
                  id: "fsm",
                  label: "State machines",
                  icon: Workflow,
                  count: fsms.length,
                },
                {
                  id: "mods",
                  label: "Modules",
                  icon: Boxes,
                  count: data.modules.length,
                },
              ]}
            />
            {tab === "tree" && (
              <Card bodyClass="p-3">
                {data.trees
                  .filter((t) => !data.unused.includes(t.module))
                  .map((t) => (
                    <TreeNode key={t.module} node={t} depth={0} root />
                  ))}
              </Card>
            )}
            {tab === "fsm" &&
              (fsm ? (
                <div className="grid gap-5 xl:grid-cols-[3fr_2fr]">
                  <Card
                    title={
                      <span className="font-mono">
                        {fsm.module}.{fsm.state_var}
                      </span>
                    }
                    subtitle={`${fsm.states.length} states · ${fsm.transitions.length} transitions · ${fsm.file}:${fsm.line}`}
                    actions={
                      fsms.length > 1 ? (
                        <div className="w-56">
                          <Select
                            value={`${fsm.module}.${fsm.state_var}`}
                            onChange={setFsmKey}
                            options={fsms.map((f) => ({
                              value: `${f.module}.${f.state_var}`,
                              label: `${f.module} · ${f.state_var}`,
                            }))}
                          />
                        </div>
                      ) : undefined
                    }
                  >
                    <StateDiagram fsm={fsm} />
                    <div className="mt-3 flex flex-wrap gap-4 text-[12.5px] text-muted">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="size-3 rounded-full border-2 border-brand" />
                        reset state
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="size-3 rounded-full border-2 border-dashed border-bad" />
                        unreachable
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="size-3 rounded-full border-2 border-warn" />
                        no way out
                      </span>
                      <span>Hover a state to highlight its arrows.</span>
                    </div>
                  </Card>
                  <div className="space-y-4">
                    {fsm.unreachable.length > 0 && (
                      <Alert tone="bad" title="Unreachable states">
                        {fsm.unreachable.join(", ")}: no path from the reset
                        state. Dead logic, or a missing transition?
                      </Alert>
                    )}
                    {fsm.dead_ends.length > 0 && (
                      <Alert tone="warn" title="States with no way out">
                        {fsm.dead_ends.join(", ")}: the FSM can get stuck here.
                      </Alert>
                    )}
                    {!fsm.unreachable.length && !fsm.dead_ends.length && (
                      <Alert
                        tone="good"
                        title="Every state is reachable and can exit"
                      />
                    )}
                    <Card title="Transitions" bodyClass="p-3">
                      <DataTable
                        rows={fsm.transitions}
                        dense
                        columns={[
                          { key: "src", header: "From", mono: true },
                          { key: "dst", header: "To", mono: true },
                          {
                            key: "condition",
                            header: "Condition",
                            mono: true,
                            wrap: true,
                          },
                        ]}
                      />
                    </Card>
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={Workflow}
                  title="No state machines found"
                  text="FSMs are detected from case(state) blocks that assign the next state."
                />
              ))}
            {tab === "mods" && (
              <Card bodyClass="p-4">
                <DataTable
                  rows={data.modules}
                  searchable
                  columns={[
                    {
                      key: "name",
                      header: "Module",
                      mono: true,
                      render: (m) => (
                        <span className="font-mono font-semibold">
                          {m.name}
                        </span>
                      ),
                    },
                    {
                      key: "file",
                      header: "File",
                      mono: true,
                      render: (m) => `${m.file}:${m.line}`,
                    },
                    {
                      key: "used",
                      header: "Instantiated",
                      align: "right",
                      render: (m) =>
                        m.used ? (
                          `${m.used}×`
                        ) : (
                          <Badge
                            tone={m.name === data.main_top ? "info" : "warn"}
                          >
                            {m.name === data.main_top ? "top" : "unused"}
                          </Badge>
                        ),
                    },
                    { key: "instances", header: "Children", align: "right" },
                    { key: "fsms", header: "FSMs", align: "right" },
                    {
                      key: "children",
                      header: "Uses",
                      wrap: true,
                      value: (m) => m.children.join(", "),
                      render: (m) => (
                        <span className="font-mono text-[12.5px] text-muted">
                          {m.children.join(", ") || "–"}
                        </span>
                      ),
                    },
                  ]}
                />
              </Card>
            )}
          </>
        )
      )}
    </>
  );
}
