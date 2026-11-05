"""Readable, coloured terminal output for the running agent (shown in the VS Code terminal).

Enabled when the environment variable ``LIBRARY_CONSOLE_LOG=1`` is set — ``run.py`` sets it for
the web server, so every decision the agent makes is printed live. Tests and the seeder stay quiet.
"""
from __future__ import annotations

import os
from typing import Any

if os.name == "nt":  # enable ANSI colours in Windows consoles
    os.system("")

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
PHASE_COLOUR = {
    "perceive": "\033[36m",  # cyan
    "think": "\033[34m",  # blue
    "act": "\033[33m",  # yellow
    "human": "\033[32m",  # green
    "system": "\033[35m",  # magenta
    "demo": "\033[95m",  # bright magenta
    "user": "\033[32m",
    "notify": "\033[93m",
}
LEVEL_COLOUR = {"Critical": "\033[91m", "High": "\033[33m", "Medium": "\033[93m", "Low": "\033[37m"}


def enabled() -> bool:
    return os.environ.get("LIBRARY_CONSOLE_LOG") == "1"


def _write(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)


def phase_line(phase: str, title: str, detail: str = "", sim_date: Any = None) -> None:
    if not enabled():
        return
    colour = PHASE_COLOUR.get(phase, "")
    date = f"{DIM}[{sim_date}]{RESET} " if sim_date else ""
    _write(f"{date}{colour}{BOLD}{phase.upper():<9}{RESET}{title}")
    if detail:
        _write(f"{'':>14}{DIM}{detail}{RESET}" if sim_date else f"{'':>9}{DIM}{detail}{RESET}")


def notification_line(level: str, kind: str, member: str, channel: str, score: float, subject: str) -> None:
    if not enabled():
        return
    colour = LEVEL_COLOUR.get(level, "")
    _write(f"{'':>14}{colour}{BOLD}{level:<8}{RESET} {kind.replace('_', ' '):<17} → {member} via {channel.replace('_', '-')} "
           f"{DIM}(score {score:.1f}){RESET}  “{subject}”")


def action_line(actor: str, action: str, entity: str, entity_id: int | None, details: dict[str, Any] | None) -> None:
    if not enabled():
        return
    info = ", ".join(f"{k}={v}" for k, v in (details or {}).items() if not isinstance(v, (dict, list)))[:160]
    target = f"{entity} #{entity_id}" if entity_id else entity
    _write(f"{PHASE_COLOUR['user']}{BOLD}{'ACTION':<9}{RESET}{actor}: {action} · {target}" + (f" {DIM}({info}){RESET}" if info else ""))


def banner(text: str) -> None:
    if enabled():
        _write(f"\n{BOLD}{'─' * 8} {text} {'─' * max(4, 60 - len(text))}{RESET}")
