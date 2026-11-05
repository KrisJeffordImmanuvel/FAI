"""Test fixtures: a seeded template database is built once and copied per test."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="library-tests-"))
os.environ["LIBRARY_DATA_DIR"] = str(_TMP)
os.environ["LIBRARY_PBKDF2_ITERATIONS"] = "1000"
os.environ["LIBRARY_SECRET"] = "test-secret"
os.environ["LIBRARY_DB_URL"] = f"sqlite:///{(_TMP / 'template.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbm  # noqa: E402

_counter = {"n": 0}


@pytest.fixture(scope="session")
def template_db() -> Path:
    from app.seed import reset_database

    reset_database(verbose=False)
    dbm.engine.dispose()
    return _TMP / "template.db"


@pytest.fixture()
def fresh_db(template_db: Path):
    _counter["n"] += 1
    target = _TMP / f"test_{_counter['n']}.db"
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(template_db) + suffix)
        if src.exists():
            shutil.copy(src, str(target) + suffix)
    dbm.configure(f"sqlite:///{target.as_posix()}")
    yield target
    dbm.engine.dispose()


@pytest.fixture()
def session(fresh_db):
    """A test-side session with ordinary deferred transactions, so reading in a
    test never holds the write lock that the API under test needs."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    eng = create_engine(f"sqlite:///{fresh_db.as_posix()}", connect_args={"check_same_thread": False, "timeout": 30})
    s = Session(eng, autoflush=True, expire_on_commit=False)
    yield s
    s.close()
    eng.dispose()


@pytest.fixture()
def client(fresh_db):
    from app.main import app

    return TestClient(app)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin_h(client):
    return login(client, "admin@library.local", "Admin@123")


@pytest.fixture()
def lib_h(client):
    return login(client, "librarian@library.local", "Librarian@123")


@pytest.fixture()
def member_h(client):
    return login(client, "member@library.local", "Member@123")
