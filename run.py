#!/usr/bin/env python3
"""One-command launcher for the Intelligent Library Circulation Agent.

    python run.py            install (first time), build, seed (first time) and serve on http://localhost:8000
    python run.py --reset    same, but wipe and re-seed the database first
    python run.py --test     run the backend (pytest) and frontend (Vitest) test suites
    python run.py --dev      hot-reload mode: API on :8000 and Vite dev server on :5173
    python run.py --no-browser   start without opening the website automatically
    python run.py --console  print every AI technique's output in the terminal (no website)
    python run.py --verbose  also show one log line per web request

The website opens in your default browser as soon as the server is ready.
In VS Code just press F5 (see .vscode/launch.json). Works on Windows, macOS and Linux.
Needs Python 3.10+ and Node.js 18+.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
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


CHILD_ENV = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}  # live logs in the terminal
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # localhost checks never go via a proxy


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env=env or CHILD_ENV)


def serve(cmd: list[str], cwd: Path) -> None:
    """Run a long-lived server and always stop it when we exit (Ctrl+C, VS Code stop button, errors)."""
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=cwd, env=CHILD_ENV)
    try:
        code = proc.wait()
    except KeyboardInterrupt:
        print("\nStopping the server…", flush=True)
        return
    finally:
        if proc.poll() is None:  # we are exiting early: stop the child too
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd)


def is_up(url: str) -> bool:
    try:
        with _NO_PROXY.open(url, timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def open_when_ready(url: str, check_url: str, enabled: bool) -> None:
    """Wait in the background until the site answers, then announce it and open the browser."""
    def worker() -> None:
        for _ in range(240):  # up to ~2 minutes
            if is_up(check_url):
                break
            time.sleep(0.5)
        else:
            return
        print(f"\n\033[1;32m✔ Website is ready: {url}\033[0m", flush=True)
        if enabled:
            print("  Opening it in your browser… (use --no-browser to skip)", flush=True)
            webbrowser.open(url)
        print("  Everything the agent perceives, decides and does is printed below as it happens.", flush=True)
        print("  Try it: Agent control → Run one cycle / Play full demo. Press Ctrl+C (or Stop in VS Code) to stop.\n", flush=True)

    threading.Thread(target=worker, daemon=True).start()


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


def _stop_on_terminate() -> None:
    """VS Code's Stop button / closing the terminal sends SIGTERM/SIGHUP: treat it like Ctrl+C so the server is shut down."""
    import signal

    def handler(_signum, _frame):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, handler)
            except (OSError, ValueError):
                pass
    if signal.getsignal(signal.SIGINT) == signal.SIG_IGN:  # e.g. started from a background shell
        signal.signal(signal.SIGINT, signal.default_int_handler)


def main() -> None:
    _safe_console()
    _stop_on_terminate()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="wipe and re-seed the database")
    ap.add_argument("--test", action="store_true", help="run all tests and exit")
    ap.add_argument("--dev", action="store_true", help="run API + Vite dev server with hot reload")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="do not open the website automatically")
    ap.add_argument("--console", action="store_true", help="print the AI outputs in the terminal (no website)")
    ap.add_argument("--verbose", action="store_true", help="also log every HTTP request")
    args = ap.parse_args()

    ensure_python()
    if args.test:
        ensure_node(build=False)
        step("Backend tests (pytest)")
        run([str(PY), "-m", "pytest", "-q"], BACKEND)
        step("Frontend tests (Vitest)")
        run([NPM, "test"], FRONTEND)
        return

    if args.console:
        seed(False)
        step("Running every AI technique and printing the results")
        run([str(PY), "-m", "app.console_demo"], BACKEND)
        return

    url = f"http://localhost:{args.port}"
    if port_in_use(args.port):
        if is_up(f"http://127.0.0.1:{args.port}/api/health"):
            step(f"The library agent is already running at {url}")
            print("  Stop the other copy first if you want to restart it (Ctrl+C in its terminal).")
            if not args.no_browser:
                webbrowser.open(url)
            return
        sys.exit(f"Port {args.port} is used by another program. Try:  python run.py --port {args.port + 10}")

    ensure_node(build=not args.dev)
    seed(args.reset)
    uvicorn = [str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.port)]
    if not args.verbose:
        uvicorn.append("--no-access-log")  # keep the terminal focused on what the agent does
    CHILD_ENV["LIBRARY_CONSOLE_LOG"] = "1"  # the server prints every agent decision live
    if args.dev:
        step(f"Starting API on :{args.port} and Vite on :5173 (Ctrl+C to stop)")
        api = subprocess.Popen(uvicorn + ["--reload"], cwd=BACKEND, env=CHILD_ENV)
        open_when_ready("http://localhost:5173", "http://127.0.0.1:5173/", not args.no_browser)
        try:
            serve([NPM, "run", "dev"], FRONTEND)
        finally:
            api.terminate()
        return
    step(f"Starting the server on {url}")
    print("  Demo logins: admin@library.local / Admin@123 · librarian@library.local / Librarian@123 · member@library.local / Member@123")
    open_when_ready(url, f"http://127.0.0.1:{args.port}/api/health", not args.no_browser)
    serve(uvicorn, BACKEND)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"\nCommand failed with exit code {exc.returncode}: {' '.join(map(str, exc.cmd))}")
