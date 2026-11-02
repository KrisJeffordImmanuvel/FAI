"""Role-based access control."""
import pytest

from .conftest import login


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@library.local", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/api/books").status_code == 401
    assert client.get("/api/books", headers={"Authorization": "Bearer forged.token"}).status_code == 401


def test_demo_accounts_are_public(client):
    r = client.get("/api/auth/demo-accounts")
    assert r.status_code == 200 and {a["role"] for a in r.json()} == {"admin", "librarian", "member"}


@pytest.mark.parametrize("method,path", [
    ("get", "/api/members"),
    ("post", "/api/loans/issue"),
    ("post", "/api/agent/run"),
    ("get", "/api/analytics/dashboard"),
    ("get", "/api/agent/events"),
    ("get", "/api/ml/summary"),
    ("post", "/api/approvals/1/decide"),
    ("get", "/api/admin/users"),
])
def test_member_cannot_use_staff_endpoints(client, member_h, method, path):
    r = client.request(method.upper(), path, headers=member_h, json=None if method == "get" else {})
    assert r.status_code == 403, (path, r.status_code)


@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/users"),
    ("put", "/api/admin/settings"),
    ("post", "/api/kb/rules"),
    ("post", "/api/ml/retrain"),
    ("put", "/api/admin/policies/student"),
])
def test_librarian_cannot_use_admin_endpoints(client, lib_h, method, path):
    r = client.request(method.upper(), path, headers=lib_h, json=None if method == "get" else {})
    assert r.status_code == 403, (path, r.status_code)


def test_member_sees_only_own_records(client, member_h, lib_h):
    me = client.get("/api/auth/me", headers=member_h).json()
    other = client.get("/api/members?q=Riya", headers=lib_h).json()["items"][0]
    assert client.get(f"/api/members/{other['id']}", headers=member_h).status_code == 403
    assert client.get(f"/api/members/{me['member_id']}", headers=member_h).status_code == 200
    loans = client.get("/api/loans?status=all", headers=member_h).json()["items"]
    assert loans and all(lo["member_id"] == me["member_id"] for lo in loans)
    assert all("risk_score" not in lo for lo in loans)  # predictions are staff-only decision support
    notes = client.get("/api/notifications", headers=member_h).json()["items"]
    assert all(n["member_id"] == me["member_id"] for n in notes)


def test_admin_can_manage(client, admin_h):
    assert client.get("/api/admin/users", headers=admin_h).status_code == 200
    r = client.post("/api/admin/users", headers=admin_h, json={"email": "new.lib@library.local", "name": "New Librarian", "role": "librarian", "password": "Secret123"})
    assert r.status_code == 201
    assert login(client, "new.lib@library.local", "Secret123")
