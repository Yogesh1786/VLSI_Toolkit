"""VLSI Toolkit HTTP API (FastAPI): the bridge between the React frontend and the backend.

Run from the project folder (--reload restarts automatically when Python code changes):
    python -m uvicorn api.main:app --port 8000 --reload

Every endpoint receives file *text* in a JSON body, calls the backend package
(vlsi_toolkit) and returns plain JSON - no analysis logic lives here. The
endpoints are grouped by design area in api/routers/. Interactive API docs:
http://localhost:8000/docs . If the React app has been built (web/dist), it is
served at http://localhost:8000/ as well.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vlsi_toolkit import __version__

from .errors import install_error_handlers
from .routers import analog, compare, general, physical, rtl, verification, workspace

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def _allow_cross_origin(app: FastAPI) -> None:
    r"""Let a web app on another address call this API (frontend on Vercel, backend on Render).

    CORS_ORIGINS        comma-separated addresses, e.g. https://vlsi-toolkit.vercel.app
    CORS_ORIGIN_REGEX   optional pattern, e.g. https://vlsi-toolkit-.*\.vercel\.app for preview deployments
    The Vite dev server (localhost:5173) is always allowed.
    """
    origins = [
        o.strip().rstrip("/")
        for o in os.environ.get("CORS_ORIGINS", "").split(",")
        if o.strip()
    ]
    origins += ["http://localhost:5173", "http://127.0.0.1:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX") or None,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=3600,
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="VLSI Toolkit API",
        version=__version__,
        description="Analysis endpoints for the VLSI Toolkit web app. Everything runs locally.",
    )
    install_error_handlers(app)
    _allow_cross_origin(app)
    for module in (general, workspace, rtl, verification, physical, analog, compare):
        app.include_router(module.router)

    # Registered after the routers: catches any /api/... address that matched no endpoint,
    # so a typo or an outdated server gives a clear JSON 404 instead of the web page (or a 405).
    @app.api_route("/api/{path:path}", methods=ALL_METHODS, include_in_schema=False)
    def unknown_endpoint(path: str, request: Request):
        return JSONResponse(
            status_code=404,
            content={
                "detail": f"Unknown API endpoint: {request.method} /api/{path}. If the toolkit was just updated, "
                "restart the API server (python -m uvicorn api.main:app --port 8000 --reload)."
            },
        )

    if WEB_DIST.is_dir():
        # The built React app. Page addresses such as /lint get index.html (client-side routing).
        # On Vercel these files are served from the CDN; API routes always take priority.
        app.frontend("/", directory=WEB_DIST, fallback="index.html")

    return app


app = create_app()
