"""Health check and bundled example files."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from vlsi_toolkit import __version__, examples_catalog, history, spice, store

API_VERSION = 7  # bump when endpoints are added or changed; the web app checks it
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

router = APIRouter(prefix="/api", tags=["General"])


@router.get("/health")
def health(request: Request):
    """Liveness + version handshake: the web app warns when the server is older than itself."""
    endpoints = sorted(
        p for p in request.app.openapi()["paths"] if p.startswith("/api/")
    )
    return {
        "ok": True,
        "version": __version__,
        "api_version": API_VERSION,
        "ngspice": bool(spice.find_ngspice()),
        "hosted": history.hosted(),
        "database": store.public_info(),
        "endpoints": endpoints,
    }


@router.get("/example")
def example(path: str):
    """Text of a bundled example file, e.g. /api/example?path=pd/demo.def"""
    target = (EXAMPLES / path).resolve()
    if EXAMPLES.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, f"example '{path}' not found")
    return {
        "name": target.name,
        "path": path,
        "text": target.read_text(encoding="utf-8", errors="replace"),
    }


@router.get("/examples")
def examples(folder: str = ""):
    """List the example files inside a folder of examples/."""
    base = (EXAMPLES / folder).resolve()
    if (
        base != EXAMPLES.resolve() and EXAMPLES.resolve() not in base.parents
    ) or not base.is_dir():
        raise HTTPException(404, f"example folder '{folder}' not found")
    return sorted(
        p.relative_to(EXAMPLES).as_posix() for p in base.iterdir() if p.is_file()
    )


@router.get("/examples/catalog")
def examples_catalog_list():
    """Every example file with a description, its design area and the tools that open it."""
    return examples_catalog.catalog()


@router.get("/examples/download")
def example_download(path: str):
    """One example as a file download."""
    try:
        target = examples_catalog.resolve(path)
    except FileNotFoundError:
        raise HTTPException(404, f"example '{path}' not found")
    return FileResponse(target, filename=target.name, media_type="text/plain")


@router.get("/examples/zip")
def examples_zip():
    """All examples as one .zip file."""
    return Response(examples_catalog.zip_bytes(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="vlsi_toolkit_examples.zip"'})
