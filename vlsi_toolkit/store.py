"""Persistent storage: MongoDB when MONGODB_URI is set, otherwise a local SQLite file.

Three collections (tables):
    snapshots  saved workspace analyses (Trends page)
    events     one record per tool run: tool, time, duration, file names/sizes, result counts, error
    feedback   messages sent with the "Feedback" button

Uploaded file *contents* are never stored, only names, sizes and result summaries.

Configuration (environment variables, or a .env file in the project folder):
    MONGODB_URI   mongodb+srv://user:password@cluster0.xxxx.mongodb.net/
    MONGODB_DB    database name (default: vlsi_toolkit)
    VT_DATA_DIR   folder of the SQLite fallback (default: ~/.vlsi_toolkit)
    VT_STORE      "sqlite" forces local storage even when MONGODB_URI is set

    get_store() -> SqliteStore | MongoStore   (same methods on both)
"""

import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path=PROJECT_DIR / ".env"):
    """Read KEY=value lines from .env into os.environ (existing variables win). No extra package needed."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


# --------------------------------------------------------------------------- SQLite
class SqliteStore:
    kind = "sqlite"

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con, con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, workspace TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '', metrics TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '{}',
                demo INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS idx_ws_ts ON snapshots (workspace, ts);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, day TEXT NOT NULL, doc TEXT NOT NULL,
                tool TEXT NOT NULL, ok INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, doc TEXT NOT NULL, rating INTEGER);
            """)

    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def info(self):
        return {"kind": self.kind, "location": str(self.path), "connected": True}

    # snapshots
    def add_snapshot(self, doc):
        with closing(self._connect()) as con, con:
            cur = con.execute(
                "INSERT INTO snapshots (ts, workspace, label, metrics, summary, demo) VALUES (?,?,?,?,?,?)",
                (doc["ts"], doc["workspace"], doc["label"], json.dumps(doc["metrics"]),
                 json.dumps(doc["summary"]), int(doc["demo"])))
            return str(cur.lastrowid)

    def list_snapshots(self, workspace=None, limit=500):
        sql, args = "SELECT * FROM snapshots", []
        if workspace:
            sql, args = sql + " WHERE workspace=?", [workspace]
        with closing(self._connect()) as con:
            rows = con.execute(sql + " ORDER BY ts DESC LIMIT ?", (*args, limit)).fetchall()
        return [{"id": str(r["id"]), "ts": r["ts"], "workspace": r["workspace"], "label": r["label"],
                 "metrics": json.loads(r["metrics"]), "summary": json.loads(r["summary"]), "demo": bool(r["demo"])}
                for r in rows]

    def workspaces(self):
        with closing(self._connect()) as con:
            return [{"workspace": r[0], "snapshots": r[1], "last": r[2]} for r in con.execute(
                "SELECT workspace, COUNT(*), MAX(ts) FROM snapshots GROUP BY workspace ORDER BY MAX(ts) DESC")]

    def delete_snapshot(self, snapshot_id):
        if not str(snapshot_id).isdigit():
            return 0
        with closing(self._connect()) as con, con:
            return con.execute("DELETE FROM snapshots WHERE id=?", (int(snapshot_id),)).rowcount

    def clear_snapshots(self, workspace, demo_only=False):
        with closing(self._connect()) as con, con:
            return con.execute("DELETE FROM snapshots WHERE workspace=?" + (" AND demo=1" if demo_only else ""),
                               (workspace,)).rowcount

    # events
    def add_event(self, doc):
        with closing(self._connect()) as con, con:
            con.execute("INSERT INTO events (ts, day, doc, tool, ok) VALUES (?,?,?,?,?)",
                        (doc["ts"], doc["day"], json.dumps(doc), doc["tool"], int(doc["ok"])))

    def events_since(self, since):
        with closing(self._connect()) as con:
            return [json.loads(r[0]) for r in con.execute("SELECT doc FROM events WHERE ts>=? ORDER BY ts", (since,))]

    def recent_events(self, limit=50, failures_only=False):
        with closing(self._connect()) as con:
            rows = con.execute("SELECT doc FROM events" + (" WHERE ok=0" if failures_only else "")
                               + " ORDER BY ts DESC LIMIT ?", (limit,))
            return [json.loads(r[0]) for r in rows]

    def count_events(self):
        with closing(self._connect()) as con:
            return con.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # feedback
    def add_feedback(self, doc):
        with closing(self._connect()) as con, con:
            cur = con.execute("INSERT INTO feedback (ts, doc, rating) VALUES (?,?,?)",
                              (doc["ts"], json.dumps(doc), doc.get("rating")))
            return str(cur.lastrowid)

    def list_feedback(self, limit=100):
        with closing(self._connect()) as con:
            return [json.loads(r[1]) | {"id": str(r[0])} for r in
                    con.execute("SELECT id, doc FROM feedback ORDER BY ts DESC LIMIT ?", (limit,))]

    def feedback_stats(self):
        with closing(self._connect()) as con:
            n, avg = con.execute("SELECT COUNT(*), AVG(rating) FROM feedback").fetchone()
        return {"count": n, "avg_rating": round(avg, 2) if avg is not None else None}


# --------------------------------------------------------------------------- MongoDB
class MongoStore:
    kind = "mongodb"

    def __init__(self, uri, db_name="vlsi_toolkit", client=None):
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, appname="vlsi-toolkit")
        self.client = client
        self.db = client[db_name]
        self.db_name = db_name
        self.host = uri.split("@")[-1].split("/")[0] if uri else "?"   # never expose the password
        self._indexes_ready = False

    def _ready(self):
        if not self._indexes_ready:
            self.db.snapshots.create_index([("workspace", 1), ("ts", -1)])
            self.db.events.create_index([("ts", -1)])
            self.db.events.create_index([("ok", 1), ("ts", -1)])
            self.db.feedback.create_index([("ts", -1)])
            self._indexes_ready = True
        return self.db

    def info(self):
        try:
            self.client.admin.command("ping")
            ok, err = True, None
        except Exception as exc:  # report, don't crash /api/health
            ok, err = False, f"{type(exc).__name__}: {str(exc)[:200]}"
        return {"kind": self.kind, "location": f"{self.host} / {self.db_name}", "connected": ok, "error": err}

    @staticmethod
    def _out(doc):
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return doc

    # snapshots
    def add_snapshot(self, doc):
        return str(self._ready().snapshots.insert_one(dict(doc)).inserted_id)

    def list_snapshots(self, workspace=None, limit=500):
        q = {"workspace": workspace} if workspace else {}
        return [self._out(d) for d in self._ready().snapshots.find(q).sort("ts", -1).limit(limit)]

    def workspaces(self):
        rows = self._ready().snapshots.aggregate([
            {"$group": {"_id": "$workspace", "snapshots": {"$sum": 1}, "last": {"$max": "$ts"}}},
            {"$sort": {"last": -1}}])
        return [{"workspace": r["_id"], "snapshots": r["snapshots"], "last": r["last"]} for r in rows]

    def delete_snapshot(self, snapshot_id):
        from bson import ObjectId
        from bson.errors import InvalidId
        try:
            oid = ObjectId(str(snapshot_id))
        except (InvalidId, TypeError):
            return 0
        return self._ready().snapshots.delete_one({"_id": oid}).deleted_count

    def clear_snapshots(self, workspace, demo_only=False):
        q = {"workspace": workspace} | ({"demo": True} if demo_only else {})
        return self._ready().snapshots.delete_many(q).deleted_count

    # events
    def add_event(self, doc):
        self._ready().events.insert_one(dict(doc))

    def events_since(self, since):
        return [self._out(d) for d in self._ready().events.find({"ts": {"$gte": since}}).sort("ts", 1)]

    def recent_events(self, limit=50, failures_only=False):
        q = {"ok": False} if failures_only else {}
        return [self._out(d) for d in self._ready().events.find(q).sort("ts", -1).limit(limit)]

    def count_events(self):
        return self._ready().events.estimated_document_count()

    # feedback
    def add_feedback(self, doc):
        return str(self._ready().feedback.insert_one(dict(doc)).inserted_id)

    def list_feedback(self, limit=100):
        return [self._out(d) for d in self._ready().feedback.find().sort("ts", -1).limit(limit)]

    def feedback_stats(self):
        rows = list(self._ready().feedback.aggregate([
            {"$group": {"_id": None, "count": {"$sum": 1}, "avg": {"$avg": "$rating"}}}]))
        if not rows:
            return {"count": 0, "avg_rating": None}
        return {"count": rows[0]["count"], "avg_rating": round(rows[0]["avg"], 2) if rows[0]["avg"] is not None else None}


# --------------------------------------------------------------------------- selection
_lock = threading.Lock()
_store = None
_store_key = None


def get_store():
    """The active store. Re-created if MONGODB_URI / VT_DATA_DIR change (tests switch them)."""
    global _store, _store_key
    load_dotenv()
    uri = os.environ.get("MONGODB_URI", "").strip()
    if "<password>" in uri or "<db_password>" in uri:
        uri = ""   # the Atlas placeholder was not replaced: fall back to SQLite instead of failing
    if os.environ.get("VT_STORE") == "sqlite":
        uri = ""   # forced local storage (the test suite sets this so it never touches the real database)
    from .history import data_dir
    key = (uri, os.environ.get("MONGODB_DB", "vlsi_toolkit"), str(data_dir()))
    with _lock:
        if _store is None or key != _store_key:
            if uri:
                _store = MongoStore(uri, key[1])
            else:
                _store = SqliteStore(Path(key[2]) / "history.db")
            _store_key = key
        return _store


def placeholder_password():
    """True when .env still contains the <password> placeholder from the Atlas dialog."""
    load_dotenv()
    uri = os.environ.get("MONGODB_URI", "")
    return "<password>" in uri or "<db_password>" in uri


def new_event(tool, endpoint, ok, status, ms, files=None, result=None, error=None, ts=None):
    ts = ts or time.time()
    return {"ts": ts, "day": _day(ts), "tool": tool, "endpoint": endpoint, "ok": bool(ok), "status": status,
            "ms": round(ms, 1), "files": files or [], "result": result or {}, "error": error}


_info_cache = {"t": 0.0, "key": None, "info": None}


def store_info(max_age=60):
    """Which database is in use and whether it answers (cached: /api/health is polled often)."""
    s = get_store()
    now = time.time()
    if _info_cache["info"] is None or _info_cache["key"] is not s or now - _info_cache["t"] > max_age:
        info = s.info()
        if placeholder_password():
            info["warning"] = "MONGODB_URI in .env still contains <password>: using local SQLite instead"
        _info_cache.update(t=now, key=s, info=info)
    return _info_cache["info"]


def public_info():
    """store_info() for anyone to see: on a hosted server, without the database address."""
    from .history import hosted

    info = dict(store_info())
    if hosted():
        info.pop("location", None)
        if info.get("error"):
            info["error"] = "database not reachable"
    return info
