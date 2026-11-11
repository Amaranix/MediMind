from app.core.security import create_token
from app.db.models import AuditLog, Role
from tests.conftest import PASSWORD, login, make_user


def test_login_success_and_me(client, db):
    make_user(db, "dr.p@demo.ma")
    headers = login(client, "dr.p@demo.ma")
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["role"] == "doctor"


def test_login_is_case_insensitive_on_email(client, db):
    make_user(db, "dr.p@demo.ma")
    r = client.post("/api/auth/login", json={"email": "DR.P@demo.ma", "password": PASSWORD})
    assert r.status_code == 200


def test_wrong_password_is_rejected_and_audited(client, db):
    make_user(db, "dr.p@demo.ma")
    r = client.post("/api/auth/login", json={"email": "dr.p@demo.ma", "password": "mauvais"})
    assert r.status_code == 401
    assert db.query(AuditLog).filter_by(action="login_failed").count() == 1


def test_inactive_user_cannot_login(client, db):
    make_user(db, "old@demo.ma", active=False)
    r = client.post("/api/auth/login", json={"email": "old@demo.ma", "password": PASSWORD})
    assert r.status_code == 401


def test_missing_or_invalid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client, db):
    user = make_user(db, "dr.p@demo.ma")
    refresh = create_token(user.id, "doctor", "refresh")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_refresh_cookie_issues_new_access_token(client, db):
    make_user(db, "dr.p@demo.ma")
    login(client, "dr.p@demo.ma")  # pose le cookie httpOnly
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_refresh_without_cookie_fails(client):
    assert client.post("/api/auth/refresh").status_code == 401


def test_deactivated_user_loses_access(client, db):
    user = make_user(db, "dr.p@demo.ma")
    headers = login(client, "dr.p@demo.ma")
    user.is_active = False
    db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_admin_creates_doctor_and_doctor_cannot_manage_users(client, db):
    make_user(db, "admin@demo.ma", Role.admin)
    make_user(db, "dr.p@demo.ma")
    admin = login(client, "admin@demo.ma")
    r = client.post("/api/users", headers=admin,
                    json={"name": "Dr Berrada", "email": "berrada@demo.ma", "password": "0123456789ab"})
    assert r.status_code == 201
    dup = {"name": "Doublon", "email": "berrada@demo.ma", "password": "0123456789ab"}
    assert client.post("/api/users", headers=admin, json=dup).status_code == 409
    doctor = login(client, "dr.p@demo.ma")
    assert client.get("/api/users", headers=doctor).status_code == 403


def test_internal_domain_email_is_accepted(client, db):
    make_user(db, "admin@medimind.local", Role.admin)
    assert login(client, "admin@medimind.local")


def test_malformed_email_is_rejected(client):
    r = client.post("/api/auth/login", json={"email": "pas-un-email", "password": "x"})
    assert r.status_code == 422
