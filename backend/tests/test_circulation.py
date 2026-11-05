"""Issue/return/renew, reservation allocation, validation and concurrency."""
import threading

from sqlalchemy import select

from app import db as dbm
from app.models import Book, Copy, Loan, Member, Reservation, User
from app.services import circulation


def _free_single_copy_book(session):
    for book in session.scalars(select(Book)):
        copies = book.copies
        if len(copies) == 1 and copies[0].status == "available" and not copies[0].barcode.startswith("DEMO"):
            return book, copies[0]
    raise AssertionError("no single-copy available book")


def _member(session, name):
    return session.scalar(select(Member).where(Member.name == name))


def test_issue_and_return_via_api(client, lib_h, session):
    book, copy = _free_single_copy_book(session)
    member = _member(session, "Kavya Joshi")
    r = client.post("/api/loans/issue", headers=lib_h, json={"member_id": member.id, "barcode": copy.barcode})
    assert r.status_code == 201, r.text
    loan = r.json()
    assert loan["status"] == "active" and loan["risk_score"] is not None and loan["risk_detail"]["factors"]
    # cannot issue the same copy twice
    r2 = client.post("/api/loans/issue", headers=lib_h, json={"member_id": _member(session, "Pooja Iyer").id, "barcode": copy.barcode})
    assert r2.status_code == 409
    r3 = client.post(f"/api/loans/{loan['id']}/return", headers=lib_h)
    assert r3.status_code == 200 and r3.json()["loan"]["status"] == "returned"


def test_input_validation(client, lib_h):
    assert client.post("/api/loans/issue", headers=lib_h, json={"member_id": 1}).status_code == 422
    assert client.post("/api/fines/1/waive", headers=lib_h, json={"amount": 5, "reason": "no"}).status_code == 422
    r = client.post("/api/members", headers=lib_h, json={"name": "X", "email": "bad", "phone": "12", "member_type": "alien", "department": "CS"})
    assert r.status_code == 422 and r.json()["errors"]


def test_reservation_queue_and_automatic_allocation(session):
    librarian = session.scalar(select(User).where(User.role == "librarian"))
    book, copy = _free_single_copy_book(session)
    borrower, first, second = (_member(session, n) for n in ("Kavya Joshi", "Ananya Reddy", "Harsh Agarwal"))
    loan = circulation.issue(session, borrower.id, librarian, copy_id=copy.id)
    r1 = circulation.reserve(session, first.id, book.id, librarian)
    r2 = circulation.reserve(session, second.id, book.id, librarian)
    assert r1.status == r2.status == "waiting"
    # renewal is blocked while others wait
    try:
        circulation.renew(session, loan.id, librarian)
        raise AssertionError("renewal should be blocked")
    except circulation.DomainError as exc:
        assert "reserved" in exc.message
    result = circulation.return_loan(session, loan.id, librarian)
    assert result["allocation"]["member_id"] == first.id  # FIFO
    session.refresh(r1)
    session.refresh(r2)
    assert r1.status == "ready" and r2.status == "waiting"
    assert session.get(Copy, copy.id).status == "on_hold"
    # the held copy cannot go to someone else
    try:
        circulation.issue(session, second.id, librarian, copy_id=copy.id)
        raise AssertionError("held copy issued to wrong member")
    except circulation.DomainError as exc:
        assert exc.status == 409
    # cancelling the hold passes it to the next member
    circulation.cancel_reservation(session, r1.id, librarian)
    session.refresh(r2)
    assert r2.status == "ready" and r2.copy_id == copy.id
    loan2 = circulation.issue(session, second.id, librarian, book_id=book.id)
    session.refresh(r2)
    assert loan2.copy_id == copy.id and r2.status == "fulfilled"
    session.commit()


def test_borrowing_limit_and_restricted_member(session):
    librarian = session.scalar(select(User).where(User.role == "librarian"))
    m = _member(session, "Zoya Ahmed")
    m.status, m.restriction_reason = "restricted", "test"
    session.flush()
    book, copy = _free_single_copy_book(session)
    try:
        circulation.issue(session, m.id, librarian, copy_id=copy.id)
        raise AssertionError
    except circulation.DomainError as exc:
        assert exc.status == 403


def test_concurrent_issue_of_same_copy_only_one_wins(session, fresh_db):
    book, copy = _free_single_copy_book(session)
    a, b = _member(session, "Kavya Joshi").id, _member(session, "Pooja Iyer").id
    librarian_id = session.scalar(select(User.id).where(User.role == "librarian"))
    session.close()
    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker(member_id: int) -> None:
        s = dbm.SessionLocal()
        try:
            barrier.wait()
            circulation.issue(s, member_id, s.get(User, librarian_id), copy_id=copy.id)
            s.commit()
            results.append("ok")
        except circulation.DomainError:
            s.rollback()
            results.append("conflict")
        except Exception as exc:  # integrity error is also a valid "loser"
            s.rollback()
            results.append(type(exc).__name__)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(m,)) for m in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1, results
    with dbm.SessionLocal() as s:
        assert len(s.scalars(select(Loan).where(Loan.copy_id == copy.id, Loan.status == "active")).all()) == 1


def test_concurrent_return_and_reservation_conflict_is_safe(session):
    """A copy returned while two members race to reserve it is held for exactly one of them."""
    librarian = session.scalar(select(User).where(User.role == "librarian"))
    book, copy = _free_single_copy_book(session)
    loan = circulation.issue(session, _member(session, "Kavya Joshi").id, librarian, copy_id=copy.id)
    session.commit()
    ids = [_member(session, n).id for n in ("Ananya Reddy", "Harsh Agarwal")]
    lib_id, loan_id = librarian.id, loan.id
    session.close()
    barrier = threading.Barrier(3)

    def reserve(mid: int) -> None:
        s = dbm.SessionLocal()
        barrier.wait()
        try:
            circulation.reserve(s, mid, book.id, s.get(User, lib_id))
            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()

    def do_return() -> None:
        s = dbm.SessionLocal()
        barrier.wait()
        circulation.return_loan(s, loan_id, s.get(User, lib_id))
        s.commit()
        s.close()

    threads = [threading.Thread(target=reserve, args=(m,)) for m in ids] + [threading.Thread(target=do_return)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with dbm.SessionLocal() as s:
        ready = s.scalars(select(Reservation).where(Reservation.book_id == book.id, Reservation.status == "ready")).all()
        assert len(ready) == 1
        assert s.get(Copy, copy.id).status == "on_hold"


def test_payment_partial_and_waiver_needs_reason(client, lib_h, member_h, session):
    from app.models import Fine

    fine = session.scalar(select(Fine).where(Fine.status.in_(("open", "accruing"))).order_by(Fine.amount.desc()))
    half = round(fine.balance / 2, 2)
    r = client.post(f"/api/fines/{fine.id}/payments", headers=lib_h, json={"amount": half, "method": "upi"})
    assert r.status_code == 200 and r.json()["amount_paid"] >= half
    over = client.post(f"/api/fines/{fine.id}/payments", headers=lib_h, json={"amount": 99999, "method": "cash"})
    assert over.status_code == 400
    bal = r.json()["balance"]
    w = client.post(f"/api/fines/{fine.id}/waive", headers=lib_h, json={"amount": bal, "reason": "Medical emergency — certificate seen"})
    assert w.status_code == 200 and w.json()["balance"] == 0
    assert w.json()["waivers"][-1]["reason"].startswith("Medical")
    # members cannot pay or waive directly
    assert client.post(f"/api/fines/{fine.id}/payments", headers=member_h, json={"amount": 1}).status_code == 403


def test_fine_preview_matches_engine(client, member_h):
    r = client.post("/api/fines/preview", headers=member_h, json={"member_type": "student", "due_on": "2026-11-02", "returned_on": "2026-11-20"})
    body = r.json()
    assert r.status_code == 200 and body["grace_days_used"] == 2 and body["total"] > 0
    assert round(sum(ln["amount"] for ln in body["lines"]), 2) == body["total"]
