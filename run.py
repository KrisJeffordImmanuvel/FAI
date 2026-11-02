#!/usr/bin/env python3
"""One-command launcher for the Intelligent Library Circulation Agent.

    python run.py            install (first time), build, seed (first time) and serve on http://localhost:8000
    python run.py --reset    same, but wipe and re-seed the database first
    python run.py --test     run the backend (pytest) and frontend (Vitest) test suites
    python run.py --dev      hot-reload mode: API on :8000 and Vite dev server on :5173

Works on Windows, macOS and Linux. Needs Python 3.10+ and Node.js 18+.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
IS_WIN = os.name == "nt"
PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
NPM = "npm.cmd" if IS_WIN else "npm"


def step(msg: str) -> None:
    print(f"\n\033[1;33m▸ {msg}\033[0m", flush=True)


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def ensure_python() -> None:
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 or newer is required.")
    marker = VENV / ".deps-installed"
    req = BACKEND / "requirements.txt"
    if not PY.exists():
        step("Creating Python virtual environment (backend/.venv)")
        venv.create(VENV, with_pip=True)
    if not marker.exists() or marker.stat().st_mtime < req.stat().st_mtime:
        step("Installing backend dependencies")
        run([str(PY), "-m", "pip", "install", "--upgrade", "pip", "-q"], BACKEND)
        run([str(PY), "-m", "pip", "install", "-r", str(req), "-q"], BACKEND)
        marker.touch()


def ensure_node(build: bool) -> None:
    if shutil.which(NPM) is None:
        sys.exit("Node.js (npm) is required: https://nodejs.org/ (version 18 or newer).")
    if not (FRONTEND / "node_modules").exists():
        step("Installing frontend dependencies")
        run([NPM, "install", "--no-audit", "--no-fund"], FRONTEND)
    if build:
        dist = FRONTEND / "dist" / "index.html"
        src_mtime = max(p.stat().st_mtime for p in (FRONTEND / "src").rglob("*") if p.is_file())
        if not dist.exists() or dist.stat().st_mtime < src_mtime:
            step("Building the frontend (production)")
            run([NPM, "run", "build"], FRONTEND)


def seed(reset: bool) -> None:
    step("Resetting and seeding the database" if reset else "Checking the database")
    run([str(PY), "-m", "app.seed"] + (["--reset"] if reset else []), BACKEND)


def _safe_console() -> None:
    """Never crash on Windows consoles that are not UTF-8 (e.g. cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _safe_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="wipe and re-seed the database")
    ap.add_argument("--test", action="store_true", help="run all tests and exit")
    ap.add_argument("--dev", action="store_true", help="run API + Vite dev server with hot reload")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    ensure_python()
    if args.test:
        ensure_node(build=False)
        step("Backend tests (pytest)")
        run([str(PY), "-m", "pytest", "-q"], BACKEND)
        step("Frontend tests (Vitest)")
        run([NPM, "test"], FRONTEND)
        return

    ensure_node(build=not args.dev)
    seed(args.reset)
    uvicorn = [str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.port)]
    if args.dev:
        step(f"Starting API on :{args.port} and Vite on :5173 (Ctrl+C to stop)")
        api = subprocess.Popen(uvicorn + ["--reload"], cwd=BACKEND)
        try:
            run([NPM, "run", "dev"], FRONTEND)
        finally:
            api.terminate()
        return
    step(f"Open http://localhost:{args.port}  (Ctrl+C to stop)")
    print("  Demo logins: admin@library.local / Admin@123 · librarian@library.local / Librarian@123 · member@library.local / Member@123")
    try:
        run(uvicorn, BACKEND)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"\nCommand failed with exit code {exc.returncode}: {' '.join(map(str, exc.cmd))}")
