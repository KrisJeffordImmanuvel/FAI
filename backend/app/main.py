"""FastAPI application entry point. Also serves the built React frontend."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, OperationalError

from . import config
from .routers import admin, agent, analytics, auth, catalog, circulation, fines, kb, members, ml, notifications
from .services.circulation import DomainError

log = logging.getLogger("library")

app = FastAPI(title="Intelligent Library Circulation Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, catalog, members, circulation, fines, notifications, agent, kb, ml, analytics, admin):
    app.include_router(r.router)


@app.exception_handler(DomainError)
async def domain_error(_req: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.exception_handler(IntegrityError)
async def integrity_error(_req: Request, exc: IntegrityError) -> JSONResponse:
    log.warning("Integrity conflict: %s", exc.orig)
    return JSONResponse({"detail": "Another action changed this record at the same time. Please refresh and try again."}, status_code=409)


@app.exception_handler(OperationalError)
async def operational_error(_req: Request, exc: OperationalError) -> JSONResponse:
    log.warning("Database busy: %s", exc.orig)
    return JSONResponse({"detail": "The database is busy — please retry in a moment."}, status_code=503)


@app.exception_handler(RequestValidationError)
async def validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]) or "body", "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
    summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors[:4])
    return JSONResponse({"detail": summary, "errors": errors}, status_code=422)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


if config.FRONTEND_DIST.exists():
    assets = config.FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        target = config.FRONTEND_DIST / full_path
        if full_path and target.is_file() and config.FRONTEND_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(config.FRONTEND_DIST / "index.html")
