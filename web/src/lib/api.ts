// Talking to the Python API (api/main.py). All analysis happens there.
import { useEffect, useRef, useState } from "react";

export type SourceFile = { name: string; text: string };

/** API version this web app was built for (see API_VERSION in api/routers/general.py). */
export const REQUIRED_API_VERSION = 5;
export const API_START_COMMAND =
  "python -m uvicorn api.main:app --port 8000 --reload";

/**
 * Where the API lives. Empty = same address as the web app (local use, Vite proxy).
 * For a separately hosted backend (e.g. Render) set VITE_API_URL at build time:
 *   VITE_API_URL=https://vlsi-toolkit-api.onrender.com
 */
export const API_BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) ?? ""
)
  .trim()
  .replace(/\/+$/, "");

const OFFLINE_MESSAGE = API_BASE
  ? `Cannot reach the API server at ${API_BASE}. A free Render server sleeps when idle and needs up to a minute to wake up: wait a moment and try again.`
  : `Cannot reach the API server. Start it with: ${API_START_COMMAND}`;

/** fetch() that adds the API address and turns a refused connection into a helpful message. */
export async function request(url: string, init?: RequestInit) {
  let r: Response;
  try {
    r = await fetch(url.startsWith("/api") ? API_BASE + url : url, init);
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new Error(OFFLINE_MESSAGE);
  }
  // the Vite dev server answers 502/504 when the API behind its proxy is down
  if (r.status === 502 || r.status === 504) throw new Error(OFFLINE_MESSAGE);
  return r;
}

async function errorMessage(r: Response) {
  // Servers older than API v2 answer unknown POST endpoints with 405: they lack this tool
  if (r.status === 405) {
    return `This API server does not know ${new URL(r.url).pathname}: it is probably outdated. Restart it with: ${API_START_COMMAND}`;
  }
  try {
    const j = await r.json();
    if (j.detail)
      return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
  } catch {
    /* not JSON */
  }
  return `${r.status} ${r.statusText}`;
}

export async function getJSON<T>(url: string): Promise<T> {
  const r = await request(url);
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}

export async function postJSON<T>(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = await request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}

export function loadExample(
  path: string,
): Promise<SourceFile & { path: string }> {
  return getJSON(`/api/example?path=${encodeURIComponent(path)}`);
}

/**
 * POST `body` to `url` whenever the body changes (debounced) and return the result.
 * Pass body = null to skip the call (e.g. while waiting for an upload).
 */
export function useAnalysis<T>(url: string, body: unknown | null, delay = 250) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const key = body == null ? null : JSON.stringify(body);
  const ctrl = useRef<AbortController | null>(null);

  useEffect(() => {
    if (key == null) {
      setData(null);
      setError(null);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      ctrl.current?.abort();
      const c = new AbortController();
      ctrl.current = c;
      try {
        const result = await postJSON<T>(url, JSON.parse(key), c.signal);
        setData(result);
        setError(null);
      } catch (e) {
        if ((e as Error).name !== "AbortError")
          setError((e as Error).message || "Request failed");
      } finally {
        if (!c.signal.aborted) setLoading(false);
      }
    }, delay);
    return () => clearTimeout(timer);
  }, [url, key, delay]);

  return { data, error, loading };
}

export type Health = {
  ok: boolean;
  version: string;
  ngspice: boolean;
  hosted?: boolean;
  api_version?: number;
  endpoints?: string[];
};

/** Polls /api/health so the app notices when the server stops, starts or is outdated. */
export function useHealth(intervalMs = 15000) {
  const [health, setHealth] = useState<Health | null>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    let alive = true;
    const check = () =>
      getJSON<Health>("/api/health")
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null))
        .finally(() => alive && setChecked(true));
    check();
    const id = setInterval(check, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [intervalMs]);
  const outdated =
    health != null && (health.api_version ?? 1) < REQUIRED_API_VERSION;
  return { health, checked, offline: checked && health == null, outdated };
}
