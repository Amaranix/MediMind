"""Assistant du dossier (F-E4) : réponses lues dans les données, citées ; refus ; recherche (modèle simulé)."""
import datetime as dt
import uuid

import numpy as np

from app.services import search as search_service
from app.services.assistant import PatientData, Rx, answer
from app.services.referential import get_referential
from app.services.trends import Point
from tests.conftest import login, make_user
from tests.test_clinical_api import bilan, validate_all
from tests.test_documents_api import setup, upload

D = dt.date.fromisoformat


def data() -> PatientData:
    bd = ("post_bd",)
    series = {"FEV1": [Point(D("2025-11-20"), 1.62, bd, None, "d1"), Point(D("2026-05-15"), 1.51, bd, None, "d2")],
              "FVC_PRED": [Point(D("2025-11-20"), 71.0, bd, None, "d1"), Point(D("2026-05-15"), 66.0, bd, None, "d2")],
              "CRP": [Point(D("2026-02-11"), 106.0, (), None, "d3"), Point(D("2026-02-25"), 6.2, (), None, "d4"),
                      Point(D("2026-03-10"), 3.1, (), None, "d5")]}
    events = [{"type": "exacerbation", "date": D("2026-02-10"), "end_date": None, "document_id": "d3"},
              {"type": "exacerbation", "date": D("2026-08-20"), "end_date": None, "document_id": "d6"}]
    rx = [Rx("amoxicilline-acide clavulanique", "antibiotic", None, D("2026-02-10"), 8, "d7"),
          Rx("lévofloxacine", "antibiotic", None, D("2026-02-24"), 10, "d8"),
          Rx("tiotropium", "lama", "2,5 µg", D("2025-11-20"), None, "d9"),
          Rx("salmétérol/fluticasone", "laba+ics", None, D("2026-03-02"), None, "d10")]
    return PatientData(series, events, rx, {})


def ask(q: str):
    return answer(get_referential(), data(), q)


def test_values_dates_and_variations_are_read_and_cited():
    a = ask("Quel était le VEMS post-bronchodilatateur le 15/05/2026 ?")
    assert a.kind == "value" and a.data["value"] == 1.51 and a.citations == ["d2"] and "1,51 L le 15/05/2026" in a.text
    a = ask("De combien le VEMS a-t-il varié entre le 20/11/2025 et le 15/05/2026 ?")
    assert a.kind == "variation" and abs(a.data["delta"] + 0.11) < 1e-9 and "−110 mL" in a.text and a.citations == ["d1", "d2"]
    a = ask("Quelle était la CVF en pourcentage de la valeur prédite le 20/11/2025 ?")
    assert a.data["param"] == "FVC_PRED" and a.data["value"] == 71
    a = ask("Quelle était la CRP lors de l'exacerbation du 10/02/2026 ?")  # bilan du lendemain
    assert a.data["value"] == 106 and "mesure la plus proche" in a.text


def test_events_treatments_and_normalisation():
    assert ask("Combien d'exacerbations le patient a-t-il présentées ?").data["count"] == 2
    a = ask("Un relais antibiotique a-t-il été nécessaire ? Si oui, par quelle molécule ?")
    assert a.data["relay"] and a.data["molecule"] == "lévofloxacine"
    a = ask("Quelle antibiothérapie a été prescrite au diagnostic, et pour combien de jours ?")
    assert a.data == {"molecule": "amoxicilline-acide clavulanique", "duration_days": 8, "date": D("2026-02-10")}
    assert ask("À quelle date le traitement a-t-il été renforcé par salmétérol/fluticasone ?").data["date"] == D("2026-03-02")
    a = ask("La CRP s'est-elle normalisée (< 5 mg/L) après l'antibiotique débuté le 10/02/2026 ?")
    assert a.data == {"normalized": True, "date": D("2026-03-10"), "value": 3.1}


def test_refusals_and_not_found():
    for q in ("Quel traitement dois-je prescrire ?", "Quel est le diagnostic ?", "Faut-il arrêter le tiotropium ?"):
        assert ask(q).kind == "refusal", q
    assert ask("Quelle est la capitale de la France ?").kind == "not_found"
    # « diagnostic » descriptif : pas un refus
    assert ask("Quelle était la CRP au diagnostic de l'exacerbation ?").kind == "value"


def test_assistant_api_cites_documents_and_keeps_history(client, db):
    h, pid = setup(client, db)
    doc = upload(client, h, pid, bilan("10/02/2026", "86")).json()[0]["document_id"]
    validate_all(client, h, doc)
    r = client.post(f"/api/patients/{pid}/assistant", headers=h, json={"question": "Quelle était la CRP le 10/02/2026 ?"})
    assert r.status_code == 200 and r.json()["kind"] == "value" and r.json()["citations"][0]["document_id"] == doc
    assert r.json()["citations"][0]["type"] == "Bilan biologique"
    r = client.post(f"/api/patients/{pid}/assistant", headers=h, json={"question": "Que dois-je prescrire ?"})
    assert r.json()["kind"] == "refusal"
    assert [m["kind"] for m in client.get(f"/api/patients/{pid}/assistant", headers=h).json()] == ["value", "refusal"]
    make_user(db, "o@demo.ma")
    assert client.post(f"/api/patients/{pid}/assistant", headers=login(client, "o@demo.ma"),
                       json={"question": "CRP ?"}).status_code == 404


def test_search_indexes_validated_documents_and_applies_threshold(client, db, monkeypatch):
    def fake_embed(texts, kind):  # vecteur selon la présence de « crp » : assez pour vérifier seuil et index
        return np.array([[1.0, 0.0] if "crp" in t.lower() or "réactive" in t.lower() else [0.0, 1.0] for t in texts])
    monkeypatch.setattr(search_service, "embed", fake_embed)
    h, pid = setup(client, db)
    doc = upload(client, h, pid, bilan("10/02/2026", "86")).json()[0]["document_id"]
    assert search_service.search(db, uuid.UUID(pid), "CRP ?") == []  # document pas encore validé : non indexé
    validate_all(client, h, doc)
    hits = search_service.search(db, uuid.UUID(pid), "Valeur de la CRP")
    assert hits and hits[0]["document_id"] == doc and "réactive" in hits[0]["text"]
    assert search_service.search(db, uuid.UUID(pid), "météo de demain") == []  # sous le seuil


def test_chunking_keeps_whole_lines():
    text = "\n".join(f"Ligne {i} " + "x" * 90 for i in range(12))
    parts = search_service.chunk(text)
    assert len(parts) > 1 and all(len(p) <= search_service.CHUNK_CHARS + 100 for p in parts)
    assert "\n".join(parts).count("Ligne") == 12
