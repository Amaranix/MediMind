import datetime as dt

from app.db.models import Job, JobStatus
from app.services import jobs as jobs_service
from tests.conftest import PATIENT, login, make_user


# ---------------------------------------------------------------- patients
def test_minor_patient_is_refused(client, db):
    make_user(db, "dr.p@demo.ma")
    h = login(client, "dr.p@demo.ma")
    birth = dt.date.today().replace(year=dt.date.today().year - 17)
    r = client.post("/api/patients", headers=h, json={**PATIENT, "birth_date": birth.isoformat()})
    assert r.status_code == 422
    assert "adultes" in r.json()["errors"][0]["message"]


def test_patient_age_is_computed(client, db):
    make_user(db, "dr.p@demo.ma")
    h = login(client, "dr.p@demo.ma")
    r = client.post("/api/patients", headers=h, json=PATIENT)
    assert r.status_code == 201
    assert r.json()["age"] >= 64


def test_patient_update_only_changes_given_fields(client, db):
    make_user(db, "dr.p@demo.ma")
    h = login(client, "dr.p@demo.ma")
    pid = client.post("/api/patients", headers=h, json=PATIENT).json()["id"]
    r = client.patch(f"/api/patients/{pid}", headers=h, json={"allergies": "Pénicilline"})
    assert r.json()["allergies"] == "Pénicilline"
    assert r.json()["pack_years"] == 40


# ---------------------------------------------------------------- jobs
def test_job_runs_to_done(db):
    user = make_user(db, "dr.p@demo.ma")
    job = jobs_service.create_job(db, "noop", None, user.id)
    jobs_service.run_job(job.id)
    db.refresh(job)
    assert job.status == JobStatus.done and job.attempts == 1 and job.finished_at


def test_failed_job_keeps_error_and_can_be_retried(client, db):
    calls = {"n": 0}

    @jobs_service.register("flaky")
    def flaky(session, job):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("OCR indisponible")

    user = make_user(db, "dr.p@demo.ma")
    job = jobs_service.create_job(db, "flaky", None, user.id)
    jobs_service.run_job(job.id)
    db.refresh(job)
    assert job.status == JobStatus.failed and "OCR indisponible" in job.error

    h = login(client, "dr.p@demo.ma")
    r = client.post(f"/api/jobs/{job.id}/retry", headers=h)
    assert r.status_code == 202
    db.expire_all()
    job = db.get(Job, job.id)
    assert job.status == JobStatus.done and job.attempts == 2


def test_job_of_another_user_is_hidden(client, db):
    owner = make_user(db, "a@demo.ma")
    make_user(db, "b@demo.ma")
    job = jobs_service.create_job(db, "noop", None, owner.id)
    assert client.get(f"/api/jobs/{job.id}", headers=login(client, "b@demo.ma")).status_code == 404
    assert client.get(f"/api/jobs/{job.id}", headers=login(client, "a@demo.ma")).status_code == 200


def test_interrupted_jobs_are_reset(db):
    db.add(Job(type="noop", status=JobStatus.running))
    db.commit()
    assert jobs_service.reset_interrupted(db) == 1
    assert db.query(Job).one().status == JobStatus.failed


# ---------------------------------------------------------------- santé
def test_health_reports_each_dependency(client):
    r = client.get("/api/health")
    body = r.json()
    assert r.status_code == 200
    assert body["database"] == "ok"
    assert body["ollama"] == "injoignable"
    assert body["referential_version"] == "0.2.0"
