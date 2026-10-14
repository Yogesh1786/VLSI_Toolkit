// Shared state of the active project workspace (one copy for the whole app).
import { useEffect, useSyncExternalStore } from "react";
import { getJSON, postJSON } from "./api";

export type WsFile = {
  path: string;
  kind: string;
  size: number;
  modified: number;
};
export type Workspace = {
  root: string;
  name: string;
  files: WsFile[];
  counts: Record<string, number>;
  kinds: Record<string, string>;
  tools: Record<string, string[]>;
  recent: string[];
  is_default: boolean;
  hosted?: boolean;
  truncated: boolean;
  scanned_at: number;
};

type State = {
  ws: Workspace | null;
  loading: boolean;
  error: string | null;
  loaded: boolean;
};
let state: State = { ws: null, loading: false, error: null, loaded: false };
const listeners = new Set<() => void>();
const set = (patch: Partial<State>) => {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
};

async function run(p: Promise<Workspace>) {
  set({ loading: true, error: null });
  try {
    set({ ws: await p, loading: false, loaded: true });
  } catch (e) {
    set({ loading: false, loaded: true, error: (e as Error).message });
    throw e;
  }
}

export const refreshWorkspace = () =>
  run(getJSON<Workspace>("/api/workspace")).catch(() => {});
export const openWorkspace = (path: string) =>
  run(postJSON<Workspace>("/api/workspace/open", { path }));
export const resetWorkspace = () =>
  run(postJSON<Workspace>("/api/workspace/reset", {}));

export function useWorkspace() {
  const s = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
  useEffect(() => {
    if (!state.loaded && !state.loading) refreshWorkspace();
  }, []);
  return s;
}

export function loadWorkspaceFile(path: string) {
  return getJSON<{ name: string; path: string; text: string }>(
    `/api/workspace/file?path=${encodeURIComponent(path)}`,
  );
}

/** Files of the workspace that a file picker accepts (by kind, or by extension). */
export function matchingFiles(
  ws: Workspace | null,
  accept?: string,
  kinds?: string[],
) {
  if (!ws) return [];
  const exts = accept
    ? accept.split(",").map((e) => e.trim().toLowerCase())
    : [];
  return ws.files
    .filter((f) =>
      kinds?.length
        ? kinds.includes(f.kind)
        : exts.length
          ? exts.some((e) => f.path.toLowerCase().endsWith(e))
          : false,
    )
    .sort((a, b) => b.modified - a.modified);
}

export const fmtSize = (n: number) =>
  n < 1024
    ? `${n} B`
    : n < 1024 ** 2
      ? `${(n / 1024).toFixed(1)} KB`
      : `${(n / 1024 ** 2).toFixed(1)} MB`;
export const fmtAgo = (t: number) => {
  const s = Date.now() / 1000 - t;
  return s < 60
    ? "just now"
    : s < 3600
      ? `${Math.floor(s / 60)} min ago`
      : s < 86400
        ? `${Math.floor(s / 3600)} h ago`
        : `${Math.floor(s / 86400)} d ago`;
};
