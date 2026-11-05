from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, staff
from ..models import Book, Copy, Loan, Reservation, User
from ..schemas import BookIn, BookUpdate, CopyIn, CopyStatusIn
from ..services.audit import audit
from ..services.settings import today

router = APIRouter(prefix="/api", tags=["catalog"])


def _counts(db: Session, book_ids: list[int]) -> tuple[dict[int, dict[str, int]], dict[int, int]]:
    counts: dict[int, dict[str, int]] = defaultdict(dict)
    if not book_ids:
        return counts, {}
    for bid, status, n in db.execute(select(Copy.book_id, Copy.status, func.count()).where(Copy.book_id.in_(book_ids)).group_by(Copy.book_id, Copy.status)):
        counts[bid][status] = n
    waiting = dict(db.execute(select(Reservation.book_id, func.count()).where(Reservation.book_id.in_(book_ids), Reservation.status == "waiting").group_by(Reservation.book_id)).all())
    return counts, waiting


@router.get("/books")
def list_books(
    q: str = Query("", max_length=100),
    category: str = Query("", max_length=60),
    availability: str = Query("", pattern="^(|available|unavailable)$"),
    sort: str = Query("title", pattern="^(title|author|year|popular)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> dict:
    query = select(Book)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Book.title.ilike(like), Book.author.ilike(like), Book.isbn.ilike(like), Book.publisher.ilike(like)))
    if category:
        query = query.where(Book.category == category)
    avail_sub = select(Copy.book_id).where(Copy.status == "available")
    if availability == "available":
        query = query.where(Book.id.in_(avail_sub))
    elif availability == "unavailable":
        query = query.where(Book.id.not_in(avail_sub))
    if sort == "popular":
        pop = select(Copy.book_id, func.count(Loan.id).label("n")).join(Loan, Loan.copy_id == Copy.id).group_by(Copy.book_id).subquery()
        query = query.outerjoin(pop, pop.c.book_id == Book.id).order_by(func.coalesce(pop.c.n, 0).desc(), Book.title)
    else:
        query = query.order_by({"title": Book.title, "author": Book.author, "year": Book.year.desc()}[sort])
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    books = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    counts, waiting = _counts(db, [b.id for b in books])
    return {"items": [S.book(b, counts.get(b.id, {}), waiting.get(b.id, 0)) for b in books], "total": total, "page": page, "page_size": page_size}


@router.get("/books/categories")
def categories(db: Session = Depends(get_db), _user: User = Depends(current_user)) -> list[dict]:
    rows = db.execute(select(Book.category, func.count()).group_by(Book.category).order_by(Book.category)).all()
    return [{"category": c, "count": n} for c, n in rows]


@router.get("/books/{book_id}")
def get_book(book_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    counts, waiting = _counts(db, [book.id])
    out = S.book(book, counts.get(book.id, {}), waiting.get(book.id, 0))
    out["copies"] = [S.copy(c) for c in book.copies]
    queue = db.scalars(select(Reservation).where(Reservation.book_id == book.id, Reservation.status.in_(("waiting", "ready"))).order_by(Reservation.created_at, Reservation.id)).all()
    pos = 0
    q_out = []
    for r in queue:
        if r.status == "waiting":
            pos += 1
        item = S.reservation(r, pos if r.status == "waiting" else None)
        if user.role == "member" and r.member_id != user.member_id:
            item["member_name"], item["member_code"] = "Another member", ""
        q_out.append(item)
    out["queue"] = q_out
    out["times_borrowed"] = db.scalar(select(func.count(Loan.id)).join(Copy, Copy.id == Loan.copy_id).where(Copy.book_id == book.id)) or 0
    if user.role != "member":
        on = today(db)
        active = db.scalars(select(Loan).join(Copy, Copy.id == Loan.copy_id).where(Copy.book_id == book.id, Loan.status == "active")).all()
        out["active_loans"] = [S.loan(lo, on) for lo in active]
    return out


@router.post("/books", status_code=201)
def create_book(body: BookIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    data = body.model_dump()
    n = data.pop("copies")
    book = Book(**data)
    db.add(book)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A book with this ISBN already exists") from None
    _add_copies(db, book, n, "NEW-1A")
    audit(db, "book.create", "book", book.id, user, {"title": book.title, "copies": n})
    db.commit()
    return S.book(book)


def _add_copies(db: Session, book: Book, n: int, shelf: str) -> None:
    last = db.scalar(select(func.max(Copy.id))) or 0
    for i in range(n):
        db.add(Copy(book_id=book.id, barcode=f"LIB-{last + i + 1 + 50000:05d}", status="available", shelf=shelf, acquired_on=date.today()))
    db.flush()


@router.put("/books/{book_id}")
def update_book(book_id: int, body: BookUpdate, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(book, k, v)
    audit(db, "book.update", "book", book.id, user, changes)
    db.commit()
    return S.book(book)


@router.post("/books/{book_id}/copies", status_code=201)
def add_copies(book_id: int, body: CopyIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    _add_copies(db, book, body.count, body.shelf)
    audit(db, "copy.add", "book", book.id, user, {"count": body.count})
    # newly added copies can satisfy the reservation queue straight away
    from ..services.circulation import allocate_copy

    for c in db.scalars(select(Copy).where(Copy.book_id == book.id, Copy.status == "available")).all():
        allocate_copy(db, c.id, reason="New copy added to the collection")
    db.commit()
    return {"copies": [S.copy(c) for c in db.get(Book, book_id).copies]}  # type: ignore[union-attr]


@router.patch("/copies/{copy_id}")
def set_copy_status(copy_id: int, body: CopyStatusIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    copy = db.get(Copy, copy_id)
    if copy is None:
        raise HTTPException(404, "Copy not found")
    allowed = {"available": ("maintenance",), "maintenance": ("available",)}
    if copy.status not in allowed[body.status]:
        raise HTTPException(409, f"Cannot change a copy that is '{copy.status}' to '{body.status}'")
    copy.status = body.status
    audit(db, "copy.status", "copy", copy.id, user, {"status": body.status})
    if body.status == "available":
        from ..services.circulation import allocate_copy

        allocate_copy(db, copy.id, reason="Copy returned from maintenance")
    db.commit()
    return S.copy(copy)
