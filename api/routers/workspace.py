"""Project workspace (a folder on this computer) and the run history."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vlsi_toolkit import history, workspace

router = APIRouter(prefix="/api", tags=["Workspace & history"])
DEFAULT_WORKSPACE = Path(__file__).resolve().parents[2] / "examples"


class OpenRequest(BaseModel):
    path: str = Field(..., min_length=1)


class AnalyzeRequest(BaseModel):
    save: bool = True
    label: str = ""


class DemoRequest(BaseModel):
    workspace: str
    days: int = Field(14, ge=2, le=90)


# ---------------------------------------------------------------- settings (remembered between sessions)


def _settings_file():
    return history.data_dir() / "settings.json"


def _settings():
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_settings(s):
    _settings_file().write_text(json.dumps(s, indent=2), encoding="utf-8")


def _current_root():
    if history.hosted():
        return str(DEFAULT_WORKSPACE)
    root = _settings().get("workspace")
    if root and Path(root).is_dir():
        return root
    return str(DEFAULT_WORKSPACE)


# ---------------------------------------------------------------- workspace


@router.get("/workspace")
def get_workspace():
    """The active workspace (the bundled examples until you open your own folder) and its files."""
    root = _current_root()
    result = workspace.scan(root)
    result["recent"] = [r for r in _settings().get("recent", []) if Path(r).is_dir()]
    result["is_default"] = Path(root).resolve() == DEFAULT_WORKSPACE.resolve()
    result["hosted"] = history.hosted()
    if result["hosted"]:
        result["root"] = "examples"  # do not reveal server paths
        result["recent"] = []
    return result


@router.post("/workspace/open")
def open_workspace(req: OpenRequest):
    if history.hosted():
        raise HTTPException(
            403,
            "Opening folders works only when the toolkit runs on your own computer. "
            "The online version shows the bundled examples; use Upload on any tool page for your files.",
        )
    path = Path(req.path.strip().strip('"')).expanduser()
    if not path.is_dir():
        raise HTTPException(404, f"Folder not found: {path}")
    root = str(path.resolve())
    s = _settings()
    s["workspace"] = root
    s["recent"] = [root] + [r for r in s.get("recent", []) if r != root][:7]
    _save_settings(s)
    return get_workspace()


@router.post("/workspace/reset")
def reset_workspace():
    """Go back to the bundled examples folder."""
    s = _settings()
    s.pop("workspace", None)
    _save_settings(s)
    return get_workspace()


@router.get("/workspace/file")
def workspace_file(path: str):
    try:
        text = workspace.read_file(_current_root(), path)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"name": Path(path).name, "path": path, "text": text}


@router.post("/workspace/analyze")
def analyze_workspace(req: AnalyzeRequest):
    root = _current_root()
    result = workspace.analyze(root)
    if req.save and result["metrics"]:
        summary = {
            "checks": result["checks"],
            "files_analyzed": result["files_analyzed"],
        }
        result["snapshot_id"] = history.save_snapshot(
            root, result["metrics"], summary, req.label
        )
    return result


# ---------------------------------------------------------------- history


@router.get("/history")
def get_history(workspace: str | None = None):
    ws = workspace or _current_root()
    return {
        "workspace": ws,
        "snapshots": history.list_snapshots(ws),
        "trends": history.trends(ws),
        "metrics": {
            k: {"label": v[0], "unit": v[1], "better": v[2], "group": v[3]}
            for k, v in history.METRIC_INFO.items()
        },
        "workspaces": history.workspaces(),
    }


@router.delete("/history/{snapshot_id}")
def delete_history(snapshot_id: int):
    if not history.delete_snapshot(snapshot_id):
        raise HTTPException(404, f"snapshot {snapshot_id} not found")
    return {"deleted": snapshot_id}


@router.delete("/history")
def clear_history(workspace: str, demo_only: bool = False):
    return {"deleted": history.clear(workspace, demo_only)}


@router.post("/history/demo")
def demo_history(req: DemoRequest):
    """Fill the history with a realistic two-week example (marked as demo) to explore the Trends page."""
    return {"added": history.seed_demo(req.workspace, req.days)}
