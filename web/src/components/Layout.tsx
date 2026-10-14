// App shell: sidebar navigation, top bar (breadcrumb, Ctrl+K search, theme toggle) and page area.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  LayoutDashboard,
  Menu,
  Monitor,
  Moon,
  Search,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import { AREAS, TOOLS, toolByPath } from "../tools";
import {
  API_START_COMMAND,
  REQUIRED_API_VERSION,
  useHealth,
  type Health,
} from "../lib/api";
import { Alert, CopyButton } from "./ui";
import { cx } from "../lib/format";

const isMac =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad/.test(navigator.platform);

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-3 px-2">
      <img src="/icon.svg" alt="" className="size-9" />
      <div className="leading-tight">
        <div className="text-[15px] font-bold text-white">VLSI Toolkit</div>
        <div className="text-[10px] font-semibold tracking-[0.14em] text-[#8fa3cc]">
          CHIP DESIGN WORKBENCH
        </div>
      </div>
    </Link>
  );
}

function Sidebar({
  onNavigate,
  health,
  outdated,
}: {
  onNavigate?: () => void;
  health: Health | null;
  outdated: boolean;
}) {
  const item = ({ isActive }: { isActive: boolean }) =>
    cx(
      "group flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
      isActive
        ? "bg-white/10 text-white shadow-[inset_2px_0_0_#7ea2ff]"
        : "text-[#aab6cf] hover:bg-white/5 hover:text-white",
    );
  return (
    <div className="flex h-full flex-col bg-[#0d1830] dark:bg-[#080d19]">
      <div className="py-5">
        <Logo />
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        <NavLink to="/" end className={item} onClick={onNavigate}>
          <LayoutDashboard className="size-4.5" /> Overview
        </NavLink>
        {AREAS.map((a) => (
          <div key={a.name}>
            <div className="mb-1.5 px-3 text-[10.5px] font-semibold tracking-[0.14em] text-[#5f6f92] uppercase">
              {a.name}
            </div>
            <div className="space-y-0.5">
              {TOOLS.filter((t) => t.area === a.name).map((t) => (
                <NavLink
                  key={t.path}
                  to={t.path}
                  className={item}
                  onClick={onNavigate}
                >
                  <t.icon className="size-4.5 opacity-90" /> {t.title}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      {/* <div className="m-3 rounded-lg border border-white/8 bg-white/4 p-3 text-[12px] text-[#9aa8c4]">
        <div className="flex items-center gap-2 font-medium text-[#cfd8ea]">
          <span
            className={cx(
              "size-2 rounded-full",
              !health
                ? "bg-[#e5484d]"
                : outdated
                  ? "bg-[#e08a00]"
                  : "bg-[#1f9d55] shadow-[0_0_0_3px_rgba(31,157,85,.25)]",
            )}
          />
          {!health
            ? "Backend offline"
            : outdated
              ? "Backend outdated"
              : "Backend connected"}
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          <ShieldCheck className="size-3.5" />
          Files never leave this computer
        </div>
        {health && (
          <div className="mt-1 text-[#6f7d9c]">
            v{health.version} · ngspice{" "}
            {health.ngspice ? "found" : "not installed"}
          </div>
        )}
      </div> */}
    </div>
  );
}

type Theme = "light" | "dark" | "system";

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("vt-theme") as Theme) || "system",
  );
  useEffect(() => {
    const apply = () => {
      const dark =
        theme === "dark" ||
        (theme === "system" &&
          matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    if (theme === "system") localStorage.removeItem("vt-theme");
    else localStorage.setItem("vt-theme", theme);
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  const opts: { v: Theme; icon: typeof Sun; label: string }[] = [
    { v: "light", icon: Sun, label: "Light" },
    { v: "dark", icon: Moon, label: "Dark" },
    { v: "system", icon: Monitor, label: "System" },
  ];
  return (
    <div className="flex rounded-lg border border-line bg-surface-2 p-0.5">
      {opts.map(({ v, icon: Icon, label }) => (
        <button
          key={v}
          title={`${label} theme`}
          onClick={() => setTheme(v)}
          className={cx(
            "grid size-7 place-items-center rounded-md transition",
            theme === v
              ? "bg-surface text-fg shadow-card"
              : "text-faint hover:text-fg",
          )}
        >
          <Icon className="size-4" />
        </button>
      ))}
    </div>
  );
}

function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const navigate = useNavigate();
  const items = useMemo(() => {
    const all = [
      {
        path: "/",
        title: "Overview",
        area: "",
        description: "Home",
        icon: LayoutDashboard,
      },
      ...TOOLS,
    ];
    const s = q.toLowerCase();
    return all.filter((t) =>
      (t.title + t.area + t.description).toLowerCase().includes(s),
    );
  }, [q]);
  useEffect(() => {
    if (open) {
      setQ("");
      setSel(0);
    }
  }, [open]);
  if (!open) return null;
  const go = (path: string) => {
    navigate(path);
    onClose();
  };
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-line bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search className="size-4.5 text-faint" />
          <input
            autoFocus
            value={q}
            placeholder="Jump to a tool…"
            className="flex-1 bg-transparent py-3.5 text-[15px] outline-none"
            onChange={(e) => {
              setQ(e.target.value);
              setSel(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSel((s) => Math.min(items.length - 1, s + 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setSel((s) => Math.max(0, s - 1));
              }
              if (e.key === "Enter" && items[sel]) go(items[sel].path);
              if (e.key === "Escape") onClose();
            }}
          />
          <kbd className="rounded border border-line px-1.5 text-[11px] text-faint">
            Esc
          </kbd>
        </div>
        <div className="max-h-80 overflow-y-auto p-1.5">
          {items.map((t, i) => (
            <button
              key={t.path}
              onMouseEnter={() => setSel(i)}
              onClick={() => go(t.path)}
              className={cx(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left",
                i === sel && "bg-brand-soft",
              )}
            >
              <t.icon
                className={cx(
                  "size-4.5",
                  i === sel ? "text-brand" : "text-faint",
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-medium">{t.title}</div>
                <div className="truncate text-[12.5px] text-muted">
                  {t.description}
                </div>
              </div>
              {t.area && (
                <span className="text-[11px] text-faint">{t.area}</span>
              )}
            </button>
          ))}
          {!items.length && (
            <div className="px-3 py-6 text-center text-[14px] text-muted">
              No matching tool
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function BackendBanner({
  offline,
  outdated,
  health,
}: {
  offline: boolean;
  outdated: boolean;
  health: Health | null;
}) {
  if (!offline && !outdated) return null;
  return (
    <Alert
      tone={offline ? "bad" : "warn"}
      title={
        offline ? "The API server is not running" : "The API server is outdated"
      }
    >
      {offline
        ? "The web app cannot reach the Python API server, so no analysis can run. Start it in a terminal from the project folder:"
        : `It was started before the latest update (server API v${health?.api_version ?? 1}, this app needs v${REQUIRED_API_VERSION}), so newer tools fail. Stop it with Ctrl+C and start it again:`}
      <div className="mt-2 flex items-center gap-2">
        <code className="rounded-md border border-line bg-surface px-2.5 py-1 font-mono text-[12.5px] text-fg">
          {API_START_COMMAND}
        </code>
        <CopyButton text={API_START_COMMAND} />
      </div>
      <div className="mt-1 text-[12.5px]">
        This message disappears automatically once the right server is running.
      </div>
    </Alert>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { health, offline, outdated } = useHealth();
  const [mobileNav, setMobileNav] = useState(false);
  const [palette, setPalette] = useState(false);
  const { pathname } = useLocation();
  const tool = toolByPath(pathname);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = tool ? `${tool.title} · VLSI Toolkit` : "VLSI Toolkit";
  }, [pathname, tool]);

  return (
    <div className="min-h-full lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Sidebar health={health} outdated={outdated} />
      </aside>
      {mobileNav && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileNav(false)}
          />
          <div className="absolute inset-y-0 left-0 w-64">
            <Sidebar
              onNavigate={() => setMobileNav(false)}
              health={health}
              outdated={outdated}
            />
            <button
              className="absolute top-5 -right-11 rounded-lg bg-surface p-2"
              onClick={() => setMobileNav(false)}
            >
              <X className="size-5" />
            </button>
          </div>
        </div>
      )}

      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur-md sm:px-6">
        <button
          className="rounded-lg p-1.5 text-muted hover:bg-surface-3 lg:hidden"
          onClick={() => setMobileNav(true)}
        >
          <Menu className="size-5" />
        </button>
        <nav className="flex min-w-0 flex-1 items-center gap-1.5 text-[13.5px] text-muted">
          <Link to="/" className="hover:text-fg">
            Workbench
          </Link>
          {tool && (
            <>
              <ChevronRight className="size-3.5 text-faint" />
              <span className="hidden sm:inline">{tool.area}</span>
              <ChevronRight className="hidden size-3.5 text-faint sm:inline" />
              <span className="truncate font-medium text-fg">{tool.title}</span>
            </>
          )}
        </nav>
        <button
          onClick={() => setPalette(true)}
          className="hidden items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] text-faint shadow-card hover:border-line-strong sm:flex"
        >
          <Search className="size-3.5" /> Search tools
          <kbd className="ml-4 rounded border border-line px-1.5 text-[11px]">
            {isMac ? "⌘ K" : "Ctrl K"}
          </kbd>
        </button>
        <ThemeToggle />
      </header>

      <main
        key={pathname}
        className="vt-fade mx-auto max-w-[1400px] px-4 py-7 sm:px-8"
      >
        <BackendBanner offline={offline} outdated={outdated} health={health} />
        {children}
      </main>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}
