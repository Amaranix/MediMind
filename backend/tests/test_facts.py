"""Dossier de faits de la fiche pré-consultation : données validées seulement, références, points à aborder."""
from app.services.facts import within_margin
from tests.conftest import login, make_user
from tests.test_clinical_api import ORDONNANCE, bilan, validate_all
from tests.test_documents_api import lab_pdf, setup, upload


def test_within_margin_rule_t29():
    assert within_margin(0.40, 0.02, 0.46, 0.01)  # 0,06 <= 2·0,0224 + 0,02 = 0,065
    assert not within_margin(0.40, 0.02, 0.48, 0.01)  # 0,08 > 0,065
    assert not within_margin(0.40, 0.01, 0.60, 0.01)


def test_facts_use_validated_data_and_cite_sources(client, db):
    h, pid = setup(client, db)
    d1 = upload(client, h, pid, bilan("15/01/2026", "4")).json()[0]["document_id"]
    d2 = upload(client, h, pid, bilan("10/02/2026", "86")).json()[0]["document_id"]
    upload(client, h, pid, bilan("20/02/2026", "30"))  # non validé : ignoré, signalé
    rx = upload(client, h, pid, lab_pdf(ORDONNANCE)).json()[0]["document_id"]
    validate_all(client, h, d1)
    validate_all(client, h, d2)
    for t in client.get(f"/api/documents/{rx}/clinical", headers=h).json()["treatments"]:
        client.patch(f"/api/treatments/{t['id']}", headers=h, json={"action": "validate"})

    f = client.get(f"/api/patients/{pid}/facts?as_of=2026-02-12", headers=h).json()
    crp = next(v for v in f["latest_values"] if v["param"] == "CRP")
    assert crp["value"] == 86 and crp["days_old"] == 2 and crp["out_of_range"]
    assert crp["document_id"] == d2 and crp["measurement_id"]
    assert crp["previous"]["value"] == 4 and crp["previous"]["delta"] == 82 and crp["previous"]["document_id"] == d1
    assert any(a["rule_id"] == "CRP_RISE" for a in f["alerts"]) and f["ruleset_version"] == "0.2.0"
    kinds = [p["kind"] for p in f["points_to_discuss"]]
    assert "alert" in kinds and "pending" in kinds
    assert {t["molecule"] for t in f["treatments"]["current"]} == {"tiotropium", "amoxicilline-acide clavulanique"}
    assert f["radiographs"] is None

    alert = next(a for a in f["alerts"] if a["rule_id"] == "CRP_RISE")
    client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=h)
    f = client.get(f"/api/patients/{pid}/facts?as_of=2026-03-01", headers=h).json()
    assert alert["id"] not in [p.get("alert_id") for p in f["points_to_discuss"]]  # acquittée : plus un point
    assert {t["molecule"] for t in f["treatments"]["current"]} == {"tiotropium"}  # antibiotique terminé

    make_user(db, "b@demo.ma")
    assert client.get(f"/api/patients/{pid}/facts", headers=login(client, "b@demo.ma")).status_code == 404
