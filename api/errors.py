"""Turn every failure into a short JSON message the frontend can show: {"detail": "..."}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("vlsi_api")


def install_error_handlers(app: FastAPI):
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        problems = []
        for err in exc.errors():
            where = (
                ".".join(str(p) for p in err.get("loc", []) if p != "body") or "body"
            )
            problems.append(f"{where}: {err.get('msg', 'invalid')}")
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request - " + "; ".join(problems)},
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        # the full traceback goes to the server console, a short message to the browser
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Internal error while handling {request.url.path}: {type(exc).__name__}: {exc}"
            },
        )
