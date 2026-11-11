"""Évolution : séries validées, alertes recalculées, frise des traitements et événements."""
import datetime as dt

from app.services.timeline import Rx, build_bars
from tests.conftest import login, make_user
from tests.test_documents_api import lab_pdf, setup, upload

D = dt.date.fromisoformat


def bilan(date: str, crp: str) -> bytes:
    return lab_pdf(["Laboratoire Atlas", f"Prélèvement du {date}", "HÉMATOLOGIE", "Leucocytes 8,4 G/L 4,0 - 10,0",
                    "Biochimie", f"Protéine C réactive {crp} mg/L < 5"])


ORDONNANCE = ["Dr Nadia Berrada, Pneumologue", "Casablanca, le 10/02/2026", "Ordonnance",
              "1. Amoxicilline-acide clavulanique 1 g/125 mg, 3 fois par jour. Pendant 7 jours.",
              "2. Tiotropium 2,5 µg, 2 inhalations le matin. Traitement au long cours."]


def validate_all(client, h, doc_id):
    return client.post(f"/api/documents/{doc_id}/validate-confident", headers=h).json()


def alert_ids(client, h, pid, scope="all"):
    return {a["rule_id"] for a in client.get(f"/api/patients/{pid}/alerts?scope={scope}", headers=h).json()}


def test_series_contains_only_validated_values(client, db):
    h, pid = setup(client, db)
    d1 = upload(client, h, pid, bilan("15/01/2026", "4")).json()[0]["document_id"]
    upload(client, h, pid, bilan("10/02/2026", "86"))
    validate_all(client, h, d1)
    s = client.get(f"/api/patients/{pid}/series?params=CRP", headers=h).json()["CRP"]
    assert [p["value"] for p in s["points"]] == [4] and [p["value"] for p in s["pending"]] == [86]
    assert s["reference"]["high"] == 5 and s["unit"] == "mg/L"


def test_alert_appears_on_validation_and_disappears_on_rejection(client, db):
    h, pid = setup(client, db)
    d1 = upload(client, h, pid, bilan("15/01/2026", "4")).json()[0]["document_id"]
    d2 = upload(client, h, pid, bilan("10/02/2026", "86")).json()[0]["document_id"]
    validate_all(client, h, d1)
    assert client.get(f"/api/patients/{pid}/alerts", headers=h).json() == []
    validate_all(client, h, d2)
    alerts = client.get(f"/api/patients/{pid}/alerts", headers=h).json()
    rise = next(a for a in alerts if a["rule_id"] == "CRP_RISE")
    assert rise["current"] and rise["values"][-1]["value"] == 86 and "Seuil biologique" in rise["source"]
    assert rise["ruleset_version"] == "0.2.0"
    ms = client.get(f"/api/documents/{d2}/measurements", headers=h).json()
    crp = next(m for m in ms if m["parameter_code"] == "CRP")
    client.patch(f"/api/measurements/{crp['id']}", headers=h, json={"action": "reject"})
    assert "CRP_RISE" not in alert_ids(client, h, pid)


def test_acknowledgement_survives_recomputation(client, db):
    h, pid = setup(client, db)
    d1 = upload(client, h, pid, bilan("15/01/2026", "4")).json()[0]["document_id"]
    d2 = upload(client, h, pid, bilan("10/02/2026", "86")).json()[0]["document_id"]
    validate_all(client, h, d1)
    validate_all(client, h, d2)
    alert = client.get(f"/api/patients/{pid}/alerts", headers=h).json()[0]
    assert client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=h).json()["state"] == "acknowledged"
    d3 = upload(client, h, pid, bilan("20/02/2026", "60")).json()[0]["document_id"]
    validate_all(client, h, d3)  # recalcul complet
    every = client.get(f"/api/patients/{pid}/alerts?scope=all", headers=h).json()
    assert next(a for a in every if a["id"] == alert["id"])["state"] == "acknowledged"
    make_user(db, "b@demo.ma")
    assert client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=login(client, "b@demo.ma")).status_code == 404


def test_prescription_becomes_treatments_on_timeline(client, db):
    h, pid = setup(client, db)
    doc = upload(client, h, pid, lab_pdf(ORDONNANCE)).json()[0]["document_id"]
    clinical = client.get(f"/api/documents/{doc}/clinical", headers=h).json()
    trt = {t["molecule"]: t for t in clinical["treatments"]}
    assert trt["amoxicilline-acide clavulanique"]["duration_days"] == 7
    assert trt["tiotropium"]["duration_days"] is None and trt["tiotropium"]["validation_status"] == "pending"
    assert client.get(f"/api/patients/{pid}/timeline", headers=h).json()["treatments"] == []  # pas encore validé
    for t in trt.values():
        client.patch(f"/api/treatments/{t['id']}", headers=h, json={"action": "validate"})
    bars = {b["molecule"]: b for b in client.get(f"/api/patients/{pid}/timeline", headers=h).json()["treatments"]}
    assert bars["amoxicilline-acide clavulanique"]["end"] == "2026-02-17"
    assert bars["tiotropium"]["end"] is None and bars["tiotropium"]["long_term"]
    assert client.get(f"/api/documents/{doc}", headers=h).json()["status"] == "validated"


def test_crp_not_normalized_needs_a_validated_antibiotic(client, db):
    h, pid = setup(client, db)
    doc = upload(client, h, pid, lab_pdf(ORDONNANCE)).json()[0]["document_id"]
    d1 = upload(client, h, pid, bilan("10/02/2026", "150")).json()[0]["document_id"]
    d2 = upload(client, h, pid, bilan("25/02/2026", "30")).json()[0]["document_id"]
    validate_all(client, h, d1)
    validate_all(client, h, d2)
    assert "CRP_NOT_NORMALIZED" not in alert_ids(client, h, pid)
    treatments = client.get(f"/api/documents/{doc}/clinical", headers=h).json()["treatments"]
    abx = next(t for t in treatments if t["drug_class"] == "antibiotic")
    client.patch(f"/api/treatments/{abx['id']}", headers=h, json={"action": "validate"})
    assert "CRP_NOT_NORMALIZED" in alert_ids(client, h, pid)


def test_manual_event_lifecycle(client, db):
    h, pid = setup(client, db)
    r = client.post(f"/api/patients/{pid}/events", headers=h,
                    json={"type": "exacerbation", "date": "2026-03-01", "note": "Appel du patient"})
    assert r.status_code == 201 and r.json()["validation_status"] == "validated"
    events = client.get(f"/api/patients/{pid}/timeline", headers=h).json()["events"]
    assert [e["type"] for e in events] == ["exacerbation"]
    future = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    bad = {"type": "exacerbation", "date": future}
    assert client.post(f"/api/patients/{pid}/events", headers=h, json=bad).status_code == 422
    assert client.delete(f"/api/events/{r.json()['id']}", headers=h).status_code == 204


def test_trends_endpoint(client, db):
    h, pid = setup(client, db)
    for date, crp in (("05/01/2026", "120"), ("08/01/2026", "50"), ("20/01/2026", "3")):
        validate_all(client, h, upload(client, h, pid, bilan(date, crp)).json()[0]["document_id"])
    crp = next(t for t in client.get(f"/api/patients/{pid}/trends", headers=h).json() if t["param"] == "CRP")
    assert crp["qualification"] == "improving" and crp["n"] == 3


# ---------------------------------------------------------------- frise (fonction pure)
def test_long_term_treatment_stops_when_not_renewed():
    rx = [Rx("tiotropium", "lama", None, D("2025-11-20"), None, "o1"),
          Rx("salbutamol", "saba", None, D("2025-11-20"), None, "o1"),
          Rx("tiotropium", "lama", None, D("2026-03-02"), None, "o2"),
          Rx("salmétérol/fluticasone", "laba+ics", None, D("2026-03-02"), None, "o2"),
          Rx("amoxicilline-acide clavulanique", "antibiotic", None, D("2026-02-10"), 7, "o3")]
    bars, changes = build_bars(rx)
    by = {b.molecule: b for b in bars}
    assert by["tiotropium"].start == D("2025-11-20") and by["tiotropium"].end is None
    assert by["salbutamol"].end == D("2026-03-02")
    assert by["amoxicilline-acide clavulanique"].end == D("2026-02-17")
    assert changes == [{"date": D("2026-03-02"), "added": ["salmétérol/fluticasone"], "stopped": ["salbutamol"]}]
