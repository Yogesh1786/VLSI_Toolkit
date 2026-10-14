"""Run history: workspace analysis snapshots stored in a local SQLite database.

The database lives in ~/.vlsi_toolkit/history.db (override with the
VT_DATA_DIR environment variable). Nothing leaves the computer.

    save_snapshot(workspace, metrics, summary, label)
    list_snapshots(workspace)      -> newest first
    trends(workspace)              -> {metric: [(timestamp, value), ...]} oldest first
"""

import json
import os
import random
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

METRIC_INFO = {  # label, unit, better ("up" / "down"), group
    "health_score": ("Health score", "%", "up", "Overall"),
    "lint_errors": ("Lint errors", "", "down", "RTL"),
    "lint_warnings": ("Lint warnings", "", "down", "RTL"),
    "rtl_modules": ("RTL modules", "", None, "RTL"),
    "fsms": ("State machines", "", None, "RTL"),
    "reg_pass_rate": ("Regression pass rate", "ratio", "up", "Verification"),
    "reg_tests": ("Regression tests", "", None, "Verification"),
    "reg_failures": ("Failing tests", "", "down", "Verification"),
    "reg_signatures": ("Unique failures", "", "down", "Verification"),
    "axi_errors": ("AXI protocol errors", "", "down", "Verification"),
    "setup_wns": ("Setup WNS", "ns", "up", "Physical design"),
    "setup_tns": ("Setup TNS", "ns", "up", "Physical design"),
    "hold_wns": ("Hold WNS", "ns", "up", "Physical design"),
    "timing_violations": ("Timing violations", "", "down", "Physical design"),
    "utilization": ("Utilization", "ratio", None, "Physical design"),
    "synth_area": ("Synthesis cell area", "", "down", "Physical design"),
    "synth_cells": ("Synthesized cells", "", None, "Physical design"),
    "power_total_mw": ("Total power", "mW", "down", "Physical design"),
    "power_leakage_mw": ("Leakage power", "mW", "down", "Physical design"),
    "sdc_errors": ("SDC errors", "", "down", "Physical design"),
    "sdc_warnings": ("SDC warnings", "", "down", "Physical design"),
    "spice_issues": ("SPICE connectivity issues", "", "down", "Analog"),
}


def hosted():
    """True when running as a public web service (Vercel sets VERCEL=1; set VT_HOSTED=1 for other hosts).
    Hosted mode only shows the bundled examples: visitors must not open folders on the server."""
    return bool(os.environ.get("VERCEL") or os.environ.get("VT_HOSTED"))


def data_dir():
    default = Path(tempfile.gettempdir()) / "vlsi_toolkit" if hosted() else Path.home() / ".vlsi_toolkit"
    d = Path(os.environ.get("VT_DATA_DIR") or default)   # hosted servers can only write to the temp folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _connect():
    con = sqlite3.connect(data_dir() / "history.db")
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        workspace TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        metrics TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '{}',
        demo INTEGER NOT NULL DEFAULT 0)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ws_ts ON snapshots (workspace, ts)")
    return con


def _row(r):
    return {"id": r["id"], "ts": r["ts"], "workspace": r["workspace"], "label": r["label"],
            "metrics": json.loads(r["metrics"]), "summary": json.loads(r["summary"]), "demo": bool(r["demo"])}


def save_snapshot(workspace, metrics, summary=None, label="", ts=None, demo=False):
    with closing(_connect()) as con, con:
        cur = con.execute("INSERT INTO snapshots (ts, workspace, label, metrics, summary, demo) VALUES (?,?,?,?,?,?)",
                          (ts or time.time(), str(workspace), label, json.dumps(metrics), json.dumps(summary or {}), int(demo)))
        return cur.lastrowid


def list_snapshots(workspace=None, limit=500):
    with closing(_connect()) as con:
        if workspace:
            rows = con.execute("SELECT * FROM snapshots WHERE workspace=? ORDER BY ts DESC LIMIT ?", (str(workspace), limit))
        else:
            rows = con.execute("SELECT * FROM snapshots ORDER BY ts DESC LIMIT ?", (limit,))
        return [_row(r) for r in rows]


def workspaces():
    with closing(_connect()) as con:
        return [{"workspace": r[0], "snapshots": r[1], "last": r[2]} for r in
                con.execute("SELECT workspace, COUNT(*), MAX(ts) FROM snapshots GROUP BY workspace ORDER BY MAX(ts) DESC")]


def delete_snapshot(snapshot_id):
    with closing(_connect()) as con, con:
        return con.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,)).rowcount


def clear(workspace, demo_only=False):
    with closing(_connect()) as con, con:
        sql = "DELETE FROM snapshots WHERE workspace=?" + (" AND demo=1" if demo_only else "")
        return con.execute(sql, (str(workspace),)).rowcount


def trends(workspace):
    series = {}
    for snap in reversed(list_snapshots(workspace)):
        for k, v in snap["metrics"].items():
            if isinstance(v, (int, float)):
                series.setdefault(k, []).append({"ts": snap["ts"], "value": v, "id": snap["id"]})
    return series


def seed_demo(workspace, days=14, base=None):
    """Insert a realistic two-week project history (marked as demo) so the Trends page can be explored."""
    rnd = random.Random(42)
    base = base or {}
    now = time.time()
    lint_e, lint_w, fails, wns, tns, axi_e = 9, 31, 14, -0.85, -6.2, 6
    for d in range(days, 0, -1):
        ts = now - d * 86400 + rnd.randint(0, 3600)
        lint_e = max(0, lint_e - rnd.choice([0, 1, 1, 2]))
        lint_w = max(2, lint_w - rnd.choice([0, 1, 2, 3]) + rnd.choice([0, 0, 1]))
        fails = max(1, fails - rnd.choice([0, 1, 2]) + (3 if d == 6 else 0))   # a bad night 6 days ago
        wns = min(-0.02, wns + rnd.uniform(0.02, 0.09) - (0.25 if d == 6 else 0))
        tns = min(-0.05, tns + rnd.uniform(0.2, 0.6) - (1.5 if d == 6 else 0))
        axi_e = max(0, axi_e - rnd.choice([0, 0, 1]))
        tests = 40 + (days - d) * 2
        m = {
            "lint_errors": lint_e, "lint_warnings": lint_w, "rtl_modules": 18 + (days - d) // 3, "fsms": 4,
            "reg_tests": tests, "reg_failures": fails, "reg_pass_rate": round((tests - fails) / tests, 4),
            "reg_signatures": max(1, fails // 3), "axi_errors": axi_e, "setup_wns": round(wns, 3),
            "setup_tns": round(tns, 3), "hold_wns": round(rnd.uniform(-0.03, 0.02), 3),
            "timing_violations": max(0, int(-tns * 2)), "utilization": round(0.52 + (days - d) * 0.006, 4),
        }
        checks = [m["lint_errors"] == 0, m["reg_failures"] == 0, m["setup_wns"] >= 0, m["axi_errors"] == 0]
        m["health_score"] = round(100 * (sum(checks) + 0.5 * (len(checks) - sum(checks))) / len(checks))
        save_snapshot(workspace, m, {"note": "demo data"}, label=f"nightly #{days - d + 1} (demo)", ts=ts, demo=True)
    return days
