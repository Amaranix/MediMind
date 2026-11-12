"""Rédaction assistée : vérificateur déterministe et repli sur le gabarit (LLM simulé)."""
from app.services import assist, llm
from tests.test_clinical_api import bilan, validate_all
from tests.test_documents_api import lab_pdf, setup, upload

SOURCE = """Patient : 64 ans, homme, tabagisme 40 paquets-années. Suivi : BPCO.
Exacerbation le 10/02/2026.
VEMS post-BD : 1,5 L le 05/11/2026, précédente 1,54 L le 17/09/2026 ; tendance sur 12 mois : dégradation (−0,125 L par an).
Rapport VEMS/CVF post-BD : 0,49 le 05/11/2026 (hors de la zone de référence) ; tendance sur 12 mois : stable.
VEMS (% prédit) post-BD : 49 % le 05/11/2026 (hors de la zone de référence) ; tendance sur 12 mois : stable.
Radiographies du 21/08/2026 et du 05/11/2026 : score indicatif d'emphysème 0,415 puis 0,501,
variation dans la marge d'incertitude."""


def test_verifier_accepts_faithful_text():
    text = ("Homme de 64 ans suivi pour BPCO, exacerbation le 10 février 2026. Le VEMS post-BD est à 1,50 L le "
            "05/11/2026, en dégradation sur 12 mois (−0,13 L par an). Le rapport VEMS/CVF est stable à 0,49. "
            "Le VEMS (% prédit) est à 49 %, hors de la zone de référence. "
            "Les scores radiographiques varient dans la marge d'incertitude.")
    r = assist.verify(text, SOURCE)
    assert r["ok"], r["issues"]
    assert r["checked"] >= 5


def test_verifier_rejects_each_kind_of_error():
    cases = {
        "Le VEMS est à 1,7 L.": "nombre absent",
        "Le VEMS est à 2 L.": "nombre absent",  # 1,54 arrondi à l'entier : refusé
        "Exacerbation le 11/02/2026.": "date absente",
        "Exacerbation en mars 2026.": "mois absent",
        "Suivi de BPCO depuis 40 ans.": "40 ans",  # bon nombre, mauvaise unité
        "Le diagnostic de BPCO est confirmé.": "diagnostic",
        "Le patient souffre de BPCO.": "souffre",
        "Pas d'argument pour une tuberculose.": "tuberculose",
        "Le rapport VEMS/CVF est en dégradation.": "rapport vems/cvf",
        "Le score d'emphysème augmente sur la radiographie.": "augmente",
        "Le VEMS post-BD (biopsie du poumon) baisse.": "sigle",
        "Le VEMS est inférieur à la zone de référence.": "zone de référence",
        "Les rapports VEMS/CVF sont stables. Le VEMS est stable.": "vems",
        "Le VEMS est à 1,5 L et les radiographies montrent": "tronqué",
    }
    for text, expected in cases.items():
        r = assist.verify(text, SOURCE)
        assert not r["ok"] and any(expected in i for i in r["issues"]), (text, r["issues"])


def _patient_with_data(client, db):
    h, pid = setup(client, db)
    for date, crp in (("15/01/2026", "4"), ("10/02/2026", "86")):
        validate_all(client, h, upload(client, h, pid, bilan(date, crp)).json()[0]["document_id"])
    return h, pid


def test_assisted_sheet_retries_then_uses_verified_text(client, db, monkeypatch):
    replies = iter(["La CRP est à 99 mg/L.", "La CRP est à 86 mg/L le 10/02/2026, précédente 4 mg/L."])
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: next(replies))
    h, pid = _patient_with_data(client, db)
    s = client.post(f"/api/patients/{pid}/sheets?as_of=2026-02-12&assisted=true", headers=h).json()
    assert s["mode"] == "llm" and [a["ok"] for a in s["attempts"]] == [False, True]
    assert "99" in s["attempts"][0]["issues"][0]
    assert "La CRP est à 86 mg/L le 10/02/2026" in s["html"] and "vérifiée" in s["html"]


def test_assisted_sheet_falls_back_to_template_after_two_failures(client, db, monkeypatch):
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: "Le diagnostic est certain.")
    h, pid = _patient_with_data(client, db)
    s = client.post(f"/api/patients/{pid}/sheets?as_of=2026-02-12&assisted=true", headers=h).json()
    assert s["mode"] == "template" and len(s["attempts"]) == 2
    assert "Rédaction assistée indisponible" in s["html"] and "diagnostic" not in s["html"].split("Aucun diagnostic")[1]
    assert "Motif et contexte" in s["html"]


def test_llm_classification_keeps_model_name_on_document(client, db, monkeypatch):
    monkeypatch.setattr(llm, "classify_document", lambda text: ("ordonnance", 0.9))
    h, pid = setup(client, db)
    pdf = lab_pdf(["Note manuscrite du 12/03/2026", "Texte sans structure reconnue"])
    doc_id = upload(client, h, pid, pdf).json()[0]["document_id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=h).json()
    assert doc["type"] == "ordonnance" and doc["type_source"] == "llm"
    assert any(llm.model_name() in w for w in doc["warnings"])
