"""Tests unitaires du pipeline d'ingestion (normalisation, extraction par règles, classification, dates).

Les documents sont construits en mémoire (mots + positions) : aucun fichier ni OCR nécessaire.
"""
import datetime as dt

import pymupdf
import pytest

from app.services.ingestion.classify import classify_rules
from app.services.ingestion.extract import extract_efr, extract_lab, extract_report, find_exam_date
from app.services.ingestion.normalize import (
    LabelMatcher,
    infer_unit_by_magnitude,
    parse_number,
    resolve_unit,
)
from app.services.ingestion.pipeline import ingest_file
from app.services.ingestion.text import DocumentText, PageText, Word
from app.services.referential import get_referential

REF = get_referential()


def doc_from_lines(lines: list[str], ocr: bool = False, conf: float = 1.0) -> DocumentText:
    words, y = [], 0.05
    for line in lines:
        x = 0.05
        for tok in line.split(" "):
            if tok:
                words.append(Word(tok, conf, 0, x, y, x + 0.01 * len(tok), y + 0.012))
                x += 0.01 * len(tok) + 0.01
        y += 0.03
    return DocumentText([PageText(0, 595, 842, ocr, words)], is_image=False)


def by_param(values):
    return {v.param: v for v in values}


# ---------------------------------------------------------------- nombres et unités
@pytest.mark.parametrize("token,expected", [
    ("15,4", 15.4), ("8.90", 8.9), ("12 400", 12400), ('"0,30', 0.3), ("...12,6", 12.6), ("(0,60", 0.6),
])
def test_parse_number(token, expected):
    assert parse_number(token)[0] == pytest.approx(expected)


@pytest.mark.parametrize("token", ["4...", "< 5", "10^9/L", "mg/L", ""])
def test_parse_number_rejects_non_values(token):
    assert parse_number(token) is None


def test_ocr_digit_fix_is_flagged():
    assert parse_number("3l0", allow_ocr_fix=True) == (310.0, True)
    assert parse_number("3l0") is None


@pytest.mark.parametrize("code,raw,unit,factor", [
    ("WBC", "/mm³", "/mm3", 0.001), ("WBC", "10³/µL", "10^3/µL", 1), ("WBC", "10^9/L", "10^9/L", 1),
    ("CRP", "mg/dL", "mg/dL", 10), ("HB", "g/L", "g/L", 0.1), ("CREAT", "µmol/L", "µmol/L", 0.1131),
    ("FEV1_FVC", "%", "%", 0.01),
])
def test_resolve_unit(code, raw, unit, factor):
    u, f, score = resolve_unit(REF.parameter(code), raw)
    assert (u, f, score) == (unit, factor, 100)


def test_ocr_damaged_unit_is_matched_approximately():
    u, f, score = resolve_unit(REF.parameter("WBC"), "10°/uL")
    assert u == "10^3/µL" and f == 1 and score < 100


def test_unit_inferred_from_magnitude():
    assert infer_unit_by_magnitude(REF.parameter("WBC"), 12400) == ("/mm3", 0.001)
    assert infer_unit_by_magnitude(REF.parameter("EOS"), 0.3) is None  # ambigu : G/L ou /mm3


# ---------------------------------------------------------------- libellés
@pytest.mark.parametrize("words,code,n", [
    (["C-réactive", "protéine", "0,25"], "CRP", 2),
    (["Protéine", "C", "réactive", "48"], "CRP", 3),
    (["Poly.", "neutrophiles", "9", "800"], "NEUT", 2),
    (["Leucocytes", "totaux", "10^9/L"], "WBC", 2),
    (["GB", "9,6"], "WBC", 1),
    (["Hemoglobine", "141"], "HB", 1),
    (["VEMS/CVF", "%", "50"], "FEV1_FVC", 1),
    (["VEMS", "L", "3,05"], "FEV1", 2),  # synonyme « VEMS (L) » du référentiel
])
def test_label_matching(words, code, n):
    m = LabelMatcher(REF).match_prefix(words)
    assert (m.code, m.n_words) == (code, n)


def test_ocr_damaged_label_matches_approximately():
    m = LabelMatcher(REF).match_prefix(["Hémogiobine", "14,4"])
    assert m.code == "HB" and m.score < 100


# ---------------------------------------------------------------- bilans : les 4 mises en page
def test_lab_table_with_thousands_and_reference_range():
    doc = doc_from_lines(["Examen Résultat Unité Valeurs usuelles", "Leucocytes 12 400 /mm³ 4000 - 10000",
                          "Protéine C réactive 48,0 mg/L < 5,0", "Hémoglobine 14,1 g/dL 12,0 - 17,0"])
    v = by_param(extract_lab(doc, REF))
    assert v["WBC"].value == pytest.approx(12.4) and v["WBC"].printed_unit == "/mm3"
    assert v["CRP"].value == 48 and v["HB"].value == 14.1


def test_lab_unit_before_value_and_decimal_point():
    doc = doc_from_lines(["Analyse Unité Résultat Référence", "Leucocytes totaux 10^9/L 8.90 4.00 - 10.00",
                          "Hemoglobine g/L 141 120 - 170", "Créatinine sérique µmol/L 81 53 - 115"])
    v = by_param(extract_lab(doc, REF))
    assert v["WBC"].value == pytest.approx(8.9)
    assert v["HB"].value == pytest.approx(14.1)
    assert v["CREAT"].value == pytest.approx(81 * 0.1131, rel=1e-3)


def test_lab_dotted_leaders_and_parenthesised_range():
    doc = doc_from_lines(["Globules blancs ........ 6,5 10³/µL (4,0 - 10,0)",
                          "C-réactive protéine ...... 0,36 mg/dL (< 0,50)"])
    v = by_param(extract_lab(doc, REF))
    assert v["WBC"].value == 6.5
    assert v["CRP"].value == pytest.approx(3.6)


def test_previous_result_column_is_ignored():
    doc = doc_from_lines(["Paramètre Valeur Unité Normes Antériorité", "CRP 6,2 mg/L < 5,0 48,0"])
    assert by_param(extract_lab(doc, REF))["CRP"].value == 6.2


def test_lost_value_does_not_fall_back_on_reference_range():
    doc = doc_from_lines(["Plaquettes ..... 10³/µL (150 - 400)"], ocr=True, conf=0.9)
    assert "PLT" not in by_param(extract_lab(doc, REF))


def test_implausible_value_is_flagged_suspect():
    doc = doc_from_lines(["Hémoglobine 229 g/dL"])
    v = by_param(extract_lab(doc, REF))["HB"]
    assert v.suspect and v.confidence <= 0.4


def test_ocr_values_never_reach_bulk_validation_threshold():
    doc = doc_from_lines(["Leucocytes 9,8 G/L 4,0 - 10,0"], ocr=True, conf=0.99)
    assert by_param(extract_lab(doc, REF))["WBC"].confidence <= 0.9


# ---------------------------------------------------------------- EFR
def test_efr_columns_and_contexts():
    lines = ["Paramètre Unité Théorique Pré-BD Post-BD % Théo (post)",
             "VEMS L 3,05 1,44 1,50 49", "CVF L 3,90 2,88 3,04 78", "VEMS/CVF % 50 49",
             "Transfert du CO : DLCO à 51 % de la valeur théorique."]
    words, y = [], 0.1
    cols = [0.05, 0.25, 0.35, 0.5, 0.62, 0.74, 0.8, 0.86]
    for li, line in enumerate(lines):
        toks = line.split(" ")
        for k, tok in enumerate(toks):
            if li in (1, 2):
                x = [0.05, 0.25, 0.35, 0.5, 0.62, 0.74][k]
            elif li == 3:
                x = [0.05, 0.25, 0.5, 0.62][k]
            elif li == 0:
                x = cols[k]
            else:
                x = 0.05 + 0.05 * k
            words.append(Word(tok, 1.0, 0, x - 0.02, y, x + 0.02, y + 0.012))
        y += 0.03
    doc = DocumentText([PageText(0, 595, 842, False, words)], is_image=False)
    got = {(v.param, tuple(v.context)): v.value for v in extract_efr(doc, REF)}
    assert got[("FEV1", ("pre_bd",))] == 1.44
    assert got[("FEV1", ("post_bd",))] == 1.50
    assert got[("FEV1_PRED", ("post_bd",))] == 49
    assert got[("FEV1_FVC", ("post_bd",))] == pytest.approx(0.49)
    assert got[("DLCO_PRED", ())] == 51
    assert ("FEV1", ()) not in got  # la colonne « Théorique » n'est jamais une mesure


def test_efr_without_readable_header_uses_value_count():
    doc = doc_from_lines(["Test de réversibilité après salbutamol", "VEMS L 3,05 1,44 1,50 49"], ocr=True, conf=0.95)
    got = {(v.param, tuple(v.context)): v for v in extract_efr(doc, REF)}
    assert got[("FEV1", ("post_bd",))].value == 1.5
    assert "columns_inferred" in got[("FEV1", ("post_bd",))].flags


# ---------------------------------------------------------------- comptes rendus et dates
def test_report_spo2_context_and_blood_gases():
    doc = doc_from_lines(["Exacerbation. SpO2 à 91 % au repos en", "air ambiant. Gaz du sang en air ambiant :",
                          "pH 7,34 ; PaO2 58 mmHg ; PaCO2 53 mmHg ; HCO3- 29 mmol/L."])
    v = by_param(extract_report(doc, REF))
    assert v["SPO2"].value == 91 and set(v["SPO2"].context) == {"rest", "room_air"}
    assert v["PH"].value == 7.34 and v["PACO2"].value == 53 and v["HCO3"].value == 29


def test_exam_date_ignores_birth_date():
    doc = doc_from_lines(["ALAOUI Karim, né(e) le 14/03/1962, Homme", "Prélèvement du 10/02/2026 à 08:20"])
    assert find_exam_date(doc) == dt.date(2026, 2, 10)


@pytest.mark.parametrize("lines,expected", [
    (["Laboratoire Atlas", "Hématologie", "Leucocytes 9", "Hémoglobine 14", "Biologiste : Dr X"], "bilan_bio"),
    (["Service d'Explorations Fonctionnelles Respiratoires", "VEMS CVF Théorique Pré-BD"], "efr"),
    (["Ordonnance", "Tiotropium 2 inhalations. Traitement au long cours."], "ordonnance"),
    (["Compte rendu de consultation", "Examen clinique : auscultation normale"], "compte_rendu"),
    (["Facture", "Montant à régler"], "inconnu"),
])
def test_classification_rules(lines, expected):
    assert classify_rules(doc_from_lines(lines)).type == expected


# ---------------------------------------------------------------- pipeline complet sur un vrai PDF
def test_pipeline_on_native_pdf(tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page()
    for i, line in enumerate(["Laboratoire Atlas d'Analyses Médicales", "Prélèvement du 21/08/2026",
                              "HÉMATOLOGIE", "Leucocytes 12,4 G/L 4,0 - 10,0", "Biochimie",
                              "Protéine C réactive 48 mg/L < 5"]):
        page.insert_text((50, 60 + 20 * i), line, fontsize=11)
    path = tmp_path / "bilan.pdf"
    pdf.save(path)
    res = ingest_file(path, "application/pdf", REF, use_llm=False)
    assert res.doc_type == "bilan_bio" and not res.text.ocr
    assert res.exam_date == dt.date(2026, 8, 21)
    v = by_param(res.values)
    assert v["WBC"].value == 12.4 and v["CRP"].value == 48
    assert v["CRP"].bbox["page"] == 0 and 0 < v["CRP"].bbox["x0"] < v["CRP"].bbox["x1"] < 1
