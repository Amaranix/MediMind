"""Dépôt, extraction en tâche de fond, consultation et validation des valeurs (F-A3 à F-A8)."""
import pymupdf

from app.db.models import AuditLog, Measurement
from tests.conftest import PATIENT, login, make_user


def lab_pdf(lines: list[str]) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page()
    for i, line in enumerate(lines):
        page.insert_text((50, 60 + 20 * i), line, fontsize=11)
    return pdf.tobytes()


BILAN = ["Laboratoire Atlas d'Analyses Médicales", "Prélèvement du 21/08/2026", "HÉMATOLOGIE",
         "Leucocytes 12,4 G/L 4,0 - 10,0", "Hémoglobine 14,1 g/dL 12,0 - 17,0", "Biochimie",
         "Protéine C réactive 48 mg/L < 5"]


def setup(client, db, email="dr.p@demo.ma"):
    make_user(db, email)
    h = login(client, email)
    pid = client.post("/api/patients", headers=h, json=PATIENT).json()["id"]
    return h, pid


def upload(client, h, pid, data: bytes, name="bilan.pdf", **form):
    return client.post(f"/api/patients/{pid}/documents", headers=h, files=[("files", (name, data, "application/pdf"))],
                       data=form)


def test_upload_extracts_values_in_background(client, db):
    h, pid = setup(client, db)
    r = upload(client, h, pid, lab_pdf(BILAN))
    assert r.status_code == 202 and r.json()[0]["status"] == "queued"
    doc_id = r.json()[0]["document_id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=h).json()
    assert doc["type"] == "bilan_bio" and doc["exam_date"] == "2026-08-21" and doc["date_source"] == "detected"
    assert doc["status"] == "extracted" and doc["pending_count"] == 3
    ms = {m["parameter_code"]: m for m in client.get(f"/api/documents/{doc_id}/measurements", headers=h).json()}
    assert ms["WBC"]["value"] == 12.4 and ms["CRP"]["value"] == 48
    assert ms["CRP"]["validation_status"] == "pending" and ms["CRP"]["bbox"]["page"] == 0


def test_duplicate_and_unsupported_files(client, db):
    h, pid = setup(client, db)
    data = lab_pdf(BILAN)
    upload(client, h, pid, data)
    assert upload(client, h, pid, data).json()[0]["status"] == "duplicate"
    txt = [("files", ("note.txt", b"bonjour", "text/plain"))]
    r = client.post(f"/api/patients/{pid}/documents", headers=h, files=txt)
    assert r.json()[0]["status"] == "rejected"


def test_pdf_disguised_as_image_is_typed_by_content(client, db):
    h, pid = setup(client, db)
    r = client.post(f"/api/patients/{pid}/documents", headers=h,
                    files=[("files", ("photo.jpg", lab_pdf(BILAN), "image/jpeg"))])
    doc = client.get(f"/api/documents/{r.json()[0]['document_id']}", headers=h).json()
    assert doc["mime_type"] == "application/pdf"


def test_documents_are_isolated_between_doctors(client, db):
    h, pid = setup(client, db)
    doc_id = upload(client, h, pid, lab_pdf(BILAN)).json()[0]["document_id"]
    make_user(db, "b@demo.ma")
    other = login(client, "b@demo.ma")
    for url in (f"/api/documents/{doc_id}", f"/api/documents/{doc_id}/file", f"/api/documents/{doc_id}/pages/0",
                f"/api/documents/{doc_id}/measurements", f"/api/patients/{pid}/documents"):
        assert client.get(url, headers=other).status_code == 404, url
    m_id = client.get(f"/api/documents/{doc_id}/measurements", headers=h).json()[0]["id"]
    assert client.patch(f"/api/measurements/{m_id}", headers=other, json={"action": "validate"}).status_code == 404


def test_bulk_validation_then_document_is_validated(client, db):
    h, pid = setup(client, db)
    doc_id = upload(client, h, pid, lab_pdf(BILAN)).json()[0]["document_id"]
    doc = client.post(f"/api/documents/{doc_id}/validate-confident", headers=h).json()
    assert doc["pending_count"] == 0 and doc["validated_count"] == 3 and doc["status"] == "validated"


def test_correction_is_bounded_and_audited(client, db):
    h, pid = setup(client, db)
    doc_id = upload(client, h, pid, lab_pdf(BILAN)).json()[0]["document_id"]
    ms = {m["parameter_code"]: m for m in client.get(f"/api/documents/{doc_id}/measurements", headers=h).json()}
    crp = ms["CRP"]["id"]
    too_high = {"action": "correct", "value": 9999}
    assert client.patch(f"/api/measurements/{crp}", headers=h, json=too_high).status_code == 422
    r = client.patch(f"/api/measurements/{crp}", headers=h, json={"action": "correct", "value": 46})
    assert r.json()["validation_status"] == "corrected" and r.json()["value"] == 46
    log = db.query(AuditLog).filter_by(action="measurement_correct").one()
    assert log.details["before"]["value"] == 48 and log.details["after"]["value"] == 46
    r = client.patch(f"/api/measurements/{ms['WBC']['id']}", headers=h, json={"action": "reject"})
    assert r.json()["validation_status"] == "rejected"


def test_user_date_wins_and_mismatch_is_reported(client, db):
    h, pid = setup(client, db)
    doc_id = upload(client, h, pid, lab_pdf(BILAN), exam_date="2026-08-20").json()[0]["document_id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=h).json()
    assert doc["exam_date"] == "2026-08-20" and doc["date_source"] == "user"
    assert any("diffère" in w for w in doc["warnings"])


def test_changing_exam_date_moves_pending_values(client, db):
    h, pid = setup(client, db)
    doc_id = upload(client, h, pid, lab_pdf(BILAN)).json()[0]["document_id"]
    client.patch(f"/api/documents/{doc_id}", headers=h, json={"exam_date": "2026-08-22"})
    dates = {m["date"] for m in client.get(f"/api/documents/{doc_id}/measurements", headers=h).json()}
    assert dates == {"2026-08-22"}


def test_same_values_in_another_document_are_not_duplicated(client, db):
    h, pid = setup(client, db)
    upload(client, h, pid, lab_pdf(BILAN))
    second = upload(client, h, pid, lab_pdf(["Copie reçue par fax", *BILAN])).json()[0]["document_id"]
    doc = client.get(f"/api/documents/{second}", headers=h).json()
    assert doc["pending_count"] == 0 and any("déjà présente" in w for w in doc["warnings"])
    assert db.query(Measurement).count() == 3


def test_page_preview_is_png(client, db):
    h, pid = setup(client, db)
    doc_id = upload(client, h, pid, lab_pdf(BILAN)).json()[0]["document_id"]
    r = client.get(f"/api/documents/{doc_id}/pages/0?width=400", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    assert client.get(f"/api/documents/{doc_id}/pages/3", headers=h).status_code == 404
