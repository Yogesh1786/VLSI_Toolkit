"""Activity log: which tools are used, how often, how fast, and what failed.

Each tool run becomes one small record (see store.new_event). Only file *names and sizes*
and result *counts* are kept, never the uploaded text itself.

    describe_request(body)        -> [{"name", "bytes"}]       from a JSON request body
    summarize_result(body)        -> {"issues": 10, "counts": {...}, ...}
    summary(days)                 -> totals, per tool, per day (for the Activity page)
"""

import time

from .store import _day, get_store

TOOLS = {
    "/api/rtl/parse": "Module Explorer",
    "/api/rtl/lint": "RTL Lint",
    "/api/rtl/hierarchy": "Hierarchy & FSM",
    "/api/rtl/regmap": "Register Map",
    "/api/verif/testbench": "Testbench Generator",
    "/api/verif/regress": "Regression Triage",
    "/api/verif/vcd": "Waveform Viewer",
    "/api/verif/axi": "AXI Protocol Checker",
    "/api/verif/sva": "Assertion Generator",
    "/api/pd/timing": "Timing (STA)",
    "/api/pd/floorplan": "Floorplan",
    "/api/pd/liberty": "Liberty Explorer",
    "/api/pd/synthesis": "Synthesis Report",
    "/api/pd/power": "Power Report",
    "/api/pd/sdc": "SDC Checker",
    "/api/analog/netlist": "Netlist Check",
    "/api/analog/sweep": "Parameter Sweep",
    "/api/analog/sweep/run": "Parameter Sweep (run)",
    "/api/analog/measure": "Waveform Measure",
    "/api/compare/regress": "Compare Runs",
    "/api/compare/timing": "Compare Runs",
    "/api/workspace/analyze": "Project Workspace",
}


def describe_request(body, limit=20):
    """File names and sizes found in a request body ({"name": ..., "text": ...} objects at any depth)."""
    found = []

    def walk(x):
        if len(found) >= limit:
            return
        if isinstance(x, dict):
            if isinstance(x.get("name"), str) and isinstance(x.get("text"), str):
                found.append({"name": x["name"][-120:], "bytes": len(x["text"].encode("utf-8", "replace"))})
            for v in x.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(body)
    return found


def summarize_result(body, max_keys=10):
    """A few numbers that describe a result: list lengths, numeric fields and any 'counts' dict."""
    if not isinstance(body, dict):
        return {}
    out = {}
    if isinstance(body.get("counts"), dict):
        out["counts"] = {k: v for k, v in body["counts"].items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    for k, v in body.items():
        if len(out) >= max_keys:
            break
        if k == "counts":
            continue
        if isinstance(v, list):
            out[k] = len(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = round(v, 4) if isinstance(v, float) else v
    return out


def summary(days=30, store=None):
    """Totals, per-tool and per-day numbers for the last `days` days."""
    store = store or get_store()
    now = time.time()
    events = store.events_since(now - days * 86400)
    by_tool, by_day = {}, {}
    for e in events:
        t = by_tool.setdefault(e["tool"], {"tool": e["tool"], "runs": 0, "failures": 0, "ms": 0.0})
        t["runs"] += 1
        t["failures"] += 0 if e["ok"] else 1
        t["ms"] += e.get("ms") or 0
        d = by_day.setdefault(e["day"], {"runs": 0, "failures": 0})
        d["runs"] += 1
        d["failures"] += 0 if e["ok"] else 1
    tools = sorted(({"tool": t["tool"], "runs": t["runs"], "failures": t["failures"],
                     "avg_ms": round(t["ms"] / t["runs"], 1)} for t in by_tool.values()), key=lambda t: -t["runs"])
    days_list = [_day(now - k * 86400) for k in range(days - 1, -1, -1)]
    runs = len(events)
    failures = sum(not e["ok"] for e in events)
    return {
        "days": days,
        "totals": {
            "runs": runs,
            "failures": failures,
            "success_rate": round((runs - failures) / runs, 4) if runs else None,
            "avg_ms": round(sum(e.get("ms") or 0 for e in events) / runs, 1) if runs else None,
            "files": sum(len(e.get("files") or []) for e in events),
            "bytes": sum(f.get("bytes", 0) for e in events for f in (e.get("files") or [])),
            "tools_used": len(tools),
            "all_time_runs": store.count_events(),
            "last_run": events[-1]["ts"] if events else None,
        },
        "by_tool": tools,
        "by_day": [{"day": d, **by_day.get(d, {"runs": 0, "failures": 0})} for d in days_list],
    }
