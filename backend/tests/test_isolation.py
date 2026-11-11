"""Isolation des données : un médecin ne voit jamais les patients d'un autre ; l'admin n'en voit aucun."""
from app.db.models import AuditLog, Role
from tests.conftest import PATIENT, login, make_user


def setup(client, db):
    make_user(db, "a@demo.ma")
    make_user(db, "b@demo.ma")
    make_user(db, "admin@demo.ma", Role.admin)
    a, b, admin = login(client, "a@demo.ma"), login(client, "b@demo.ma"), login(client, "admin@demo.ma")
    pid = client.post("/api/patients", headers=a, json=PATIENT).json()["id"]
    return a, b, admin, pid


def test_other_doctor_gets_404(client, db):
    a, b, _, pid = setup(client, db)
    assert client.get(f"/api/patients/{pid}", headers=a).status_code == 200
    assert client.get(f"/api/patients/{pid}", headers=b).status_code == 404
    assert client.patch(f"/api/patients/{pid}", headers=b, json={"allergies": "x"}).status_code == 404


def test_lists_are_separated(client, db):
    a, b, _, _ = setup(client, db)
    assert len(client.get("/api/patients", headers=a).json()) == 1
    assert client.get("/api/patients", headers=b).json() == []


def test_admin_has_no_access_to_patients(client, db):
    _, _, admin, pid = setup(client, db)
    assert client.get("/api/patients", headers=admin).status_code == 403
    assert client.get(f"/api/patients/{pid}", headers=admin).status_code == 403
    assert client.post("/api/patients", headers=admin, json=PATIENT).status_code == 403


def test_patient_access_is_audited(client, db):
    a, _, _, pid = setup(client, db)
    client.get(f"/api/patients/{pid}", headers=a)
    actions = {x.action for x in db.query(AuditLog).filter_by(object_id=pid)}
    assert {"patient_create", "patient_read"} <= actions
