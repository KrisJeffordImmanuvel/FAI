"""Database engine/session management.

SQLite is configured so every transaction starts with ``BEGIN IMMEDIATE``. That
takes the write lock up front, which serialises concurrent circulation actions
(two librarians returning/issuing the same copy, a reservation racing a
return) instead of letting them interleave. Partial unique indexes in the
models provide a second line of defence.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


engine: Engine
SessionLocal: sessionmaker[Session]


def _make_engine(url: str) -> Engine:
    eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15}, future=True)

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        dbapi_conn.isolation_level = None  # we emit BEGIN ourselves
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.close()

    @event.listens_for(eng, "begin")
    def _on_begin(conn):  # type: ignore[no-untyped-def]
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return eng


def configure(url: str | None = None) -> None:
    """(Re)create the engine. Used at start-up and by tests."""
    global engine, SessionLocal
    try:
        engine.dispose()  # type: ignore[has-type]
    except NameError:
        pass
    engine = _make_engine(url or config.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


configure()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)


def drop_all() -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine)
