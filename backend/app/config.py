"""Application configuration. Everything runs locally; no external services."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("LIBRARY_DATA_DIR", BACKEND_DIR / "data"))
MODELS_DIR = DATA_DIR / "models"
FRONTEND_DIST = REPO_DIR / "frontend" / "dist"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("LIBRARY_DB_URL", f"sqlite:///{(DATA_DIR / 'library.db').as_posix()}")

# PBKDF2 iterations (tests lower this through the environment to stay fast).
PASSWORD_ITERATIONS = int(os.environ.get("LIBRARY_PBKDF2_ITERATIONS", "120000"))
TOKEN_TTL_HOURS = 12


def _load_secret() -> str:
    env = os.environ.get("LIBRARY_SECRET")
    if env:
        return env
    path = DATA_DIR / ".secret"
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_hex(32)
    path.write_text(value)
    return value


SECRET_KEY = _load_secret()
CURRENCY = "₹"
