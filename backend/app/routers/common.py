"""Shared router helpers."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select


def paginate(db: Session, query: Select, page: int, page_size: int, serialize: Any) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": [serialize(r) for r in rows], "total": total, "page": page, "page_size": page_size}
