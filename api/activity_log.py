"""Records one activity event per tool run (POST to an analysis endpoint).

A plain ASGI middleware: it copies the request and response bytes as they pass, then
summarizes them in a background thread (file names/sizes + result counts, never file
contents). Logging problems are swallowed: they must never break or slow a request.
"""

import asyncio
import json
import logging
import threading
import time

from vlsi_toolkit import activity, store

log = logging.getLogger("vlsi_toolkit.activity")
MAX_CAPTURE = 25 * 1024 * 1024      # bigger bodies are passed through but not summarized
REPEAT_WINDOW = 30                  # same tool + same files within 30 s counts once (live editing, toggles)

_recent: dict[tuple, float] = {}
_recent_lock = threading.Lock()


def _is_repeat(key):
    now = time.time()
    with _recent_lock:
        for k in [k for k, t in _recent.items() if now - t > REPEAT_WINDOW]:
            del _recent[k]
        if key in _recent:
            _recent[key] = now
            return True
        _recent[key] = now
        return False


def _record(endpoint, status, ms, req_bytes, resp_bytes):
    try:
        try:
            req = json.loads(req_bytes) if req_bytes else {}
        except ValueError:
            req = {}
        try:
            resp = json.loads(resp_bytes) if resp_bytes else {}
        except ValueError:
            resp = {}
        files = activity.describe_request(req)
        if _is_repeat((endpoint, tuple(f["name"] for f in files))):
            return
        error = None
        if status >= 400 or (isinstance(resp, dict) and isinstance(resp.get("error"), str)):
            detail = resp.get("detail") if isinstance(resp, dict) else None
            error = str(detail if detail is not None else resp.get("error", f"HTTP {status}"))[:300]
        store.get_store().add_event(store.new_event(
            activity.TOOLS[endpoint], endpoint, error is None, status, ms, files,
            activity.summarize_result(resp) if error is None else {}, error))
    except Exception:  # noqa: BLE001 - logging must never fail a request
        log.exception("could not record activity for %s", endpoint)


class ActivityLogger:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in activity.TOOLS:
            await self.app(scope, receive, send)
            return
        req, resp, status = bytearray(), bytearray(), {"code": 500}
        too_big = {"req": False, "resp": False}
        start = time.perf_counter()

        async def receive_copy():
            msg = await receive()
            if msg["type"] == "http.request" and not too_big["req"]:
                req.extend(msg.get("body", b""))
                if len(req) > MAX_CAPTURE:
                    too_big["req"] = True
                    req.clear()
            return msg

        async def send_copy(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            elif msg["type"] == "http.response.body" and not too_big["resp"]:
                resp.extend(msg.get("body", b""))
                if len(resp) > MAX_CAPTURE:
                    too_big["resp"] = True
                    resp.clear()
            await send(msg)

        try:
            await self.app(scope, receive_copy, send_copy)
        finally:
            ms = (time.perf_counter() - start) * 1000
            try:
                asyncio.get_running_loop().run_in_executor(
                    None, _record, scope["path"], status["code"], ms, bytes(req), bytes(resp))
            except RuntimeError:
                pass
