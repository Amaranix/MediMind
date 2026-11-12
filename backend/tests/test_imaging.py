"""Imagerie (F-C1 à F-C3) : analyse au dépôt, contrôles de qualité, Grad-CAM, vue déclarée, isolation.

Un faux modèle remplace le réseau de neurones (tests rapides, sans téléchargement de poids). Le vrai modèle
est testé seulement si ses poids sont déjà présents sur la machine.
"""
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.services import imaging
from tests.conftest import login, make_user
from tests.test_documents_api import setup

ROOT = Path(__file__).resolve().parents[2]


def xray_png(size=(800, 800), color=False) -> bytes:
    h, w = size
    yy, xx = np.mgrid[0:h, 0:w]
    lungs = 200 - 120 * np.exp(-(((xx - w * 0.33) / (w * 0.13)) ** 2 + ((yy - h * 0.5) / (h * 0.28)) ** 2)) \
        - 120 * np.exp(-(((xx - w * 0.67) / (w * 0.13)) ** 2 + ((yy - h * 0.5) / (h * 0.28)) ** 2))
    arr = np.clip(lungs, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    if color:
        rgb = np.stack([arr, (arr * 0.4).astype(np.uint8), 255 - arr], axis=-1)
        img = Image.fromarray(rgb, "RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def fake_model(monkeypatch):
    calls = {"analyze": 0}

    def fake_analyze(path):
        calls["analyze"] += 1
        _, flags = imaging.load_gray(path)
        return imaging.XrayResult({p: 0.1 for p in imaging.SHOWN} | {"Consolidation": 0.62},
                                  {p: 0.02 for p in imaging.SHOWN}, flags, imaging.MODEL_NAME, "test 0.0")

    def fake_gradcam(path, pathology):
        buf = io.BytesIO()
        Image.new("RGBA", (8, 8), (250, 230, 90, 180)).save(buf, "PNG")
        return buf.getvalue()

    monkeypatch.setattr(imaging, "analyze", fake_analyze)
    monkeypatch.setattr(imaging, "gradcam_overlay", fake_gradcam)
    return calls


def upload_xray(client, h, pid, data, name="radio.png", exam_date="2026-02-11"):
    r = client.post(f"/api/patients/{pid}/documents", headers=h, files=[("files", (name, data, "image/png"))],
                    data={"exam_date": exam_date})
    return r.json()[0]["document_id"]


def test_radiograph_is_analysed_on_upload(client, db, fake_model):
    h, pid = setup(client, db)
    doc_id = upload_xray(client, h, pid, xray_png())
    doc = client.get(f"/api/documents/{doc_id}", headers=h).json()
    assert doc["type"] == "radiographie" and doc["status"] == "validated"
    items = client.get(f"/api/patients/{pid}/imaging", headers=h).json()["items"]
    assert items[0]["analyzed"] and items[0]["scores"]["Consolidation"] == 0.62
    assert items[0]["uncertainty"]["Consolidation"] == 0.02 and items[0]["date"] == "2026-02-11"
    assert items[0]["model_name"] == "densenet121-res224-all" and items[0]["view"] == "face"
    timeline = client.get(f"/api/patients/{pid}/timeline", headers=h).json()
    assert [r["date"] for r in timeline["radiographs"]] == ["2026-02-11"]


def test_quality_flags(client, db, fake_model):
    h, pid = setup(client, db)
    upload_xray(client, h, pid, xray_png((300, 300)), "petite.png")
    upload_xray(client, h, pid, xray_png(color=True), "couleur.png", "2026-03-01")
    flags = {i["name"]: i["quality_flags"] for i in client.get(f"/api/patients/{pid}/imaging", headers=h).json()["items"]}
    assert "resolution_faible" in flags["petite.png"]
    assert "couleur" in flags["couleur.png"]


def test_gradcam_and_view_update(client, db, fake_model):
    h, pid = setup(client, db)
    doc_id = upload_xray(client, h, pid, xray_png())
    r = client.get(f"/api/documents/{doc_id}/gradcam?pathology=Consolidation", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    assert client.get(f"/api/documents/{doc_id}/gradcam?pathology=Hernia", headers=h).status_code == 422
    r = client.patch(f"/api/documents/{doc_id}/imaging", headers=h, json={"view": "profil", "doctor_assessment": "Vue latérale"})
    assert r.json()["view"] == "profil" and r.json()["doctor_assessment"] == "Vue latérale"


def test_analysis_failure_never_blocks_upload(client, db, monkeypatch):
    def broken(path):
        raise RuntimeError("poids absents")
    monkeypatch.setattr(imaging, "analyze", broken)
    h, pid = setup(client, db)
    doc_id = upload_xray(client, h, pid, xray_png())
    doc = client.get(f"/api/documents/{doc_id}", headers=h).json()
    assert doc["type"] == "radiographie" and any("indisponible" in w for w in doc["warnings"])


def test_imaging_is_isolated_between_doctors(client, db, fake_model):
    h, pid = setup(client, db)
    doc_id = upload_xray(client, h, pid, xray_png())
    make_user(db, "b@demo.ma")
    other = login(client, "b@demo.ma")
    assert client.get(f"/api/documents/{doc_id}/gradcam?pathology=Consolidation", headers=other).status_code == 404
    assert client.patch(f"/api/documents/{doc_id}/imaging", headers=other, json={"view": "profil"}).status_code == 404
    assert client.get(f"/api/patients/{pid}/imaging", headers=other).status_code == 404


def test_variant_keeps_shape_and_range():
    x = np.random.default_rng(0).uniform(-1024, 1024, (224, 224)).astype(np.float32)
    for v in imaging.TTA:
        out = imaging._variant(x, *v)
        assert out.shape == (224, 224) and out.min() >= -1024 and out.max() <= 1024


WEIGHTS = list((Path.home() / ".torchxrayvision" / "models_data").glob("*kaggle-densenet121*"))
NIH = sorted((ROOT / "data" / "nih_subset" / "images").glob("*.png"))


@pytest.mark.skipif(not WEIGHTS or not NIH, reason="poids du modèle ou images NIH absents sur cette machine")
def test_real_model_scores_and_gradcam():
    res = imaging.analyze(NIH[0])
    assert set(res.scores) == set(imaging.SHOWN)
    assert all(0 <= v <= 1 for v in res.scores.values())
    assert all(0 <= v < 0.5 for v in res.uncertainty.values())
    png = imaging.gradcam_overlay(NIH[0], "Consolidation")
    over = Image.open(io.BytesIO(png))
    assert over.mode == "RGBA" and over.size == Image.open(NIH[0]).size
    assert np.asarray(over)[..., 3].max() > 0  # la carte n'est pas vide


def test_annotations_are_validated_and_stored(client, db, fake_model):
    h, pid = setup(client, db)
    doc_id = upload_xray(client, h, pid, xray_png())
    notes = [{"type": "arrow", "x1": 0.2, "y1": 0.3, "x2": 0.4, "y2": 0.5},
             {"type": "text", "x1": 0.5, "y1": 0.5, "text": "Opacité ?"}]
    r = client.patch(f"/api/documents/{doc_id}/imaging", headers=h, json={"annotations": notes})
    assert r.status_code == 200 and r.json()["annotations"] == notes
    assert client.patch(f"/api/documents/{doc_id}/imaging", headers=h,
                        json={"annotations": [{"type": "arrow", "x1": 0.2, "y1": 0.3}]}).status_code == 422
    assert client.patch(f"/api/documents/{doc_id}/imaging", headers=h,
                        json={"annotations": [{"type": "text", "x1": 1.5, "y1": 0.3, "text": "x"}]}).status_code == 422
    items = client.get(f"/api/patients/{pid}/imaging", headers=h).json()["items"]
    assert items[0]["annotations"] == notes


def test_doctor_qualifies_comparison_and_sheet_shows_it(client, db, fake_model):
    h, pid = setup(client, db)
    old = upload_xray(client, h, pid, xray_png(), "r1.png", "2026-02-11")
    new = upload_xray(client, h, pid, xray_png((820, 800)), "r2.png", "2026-05-15")  # autre image (pas de doublon)
    # ordre inversé à l'envoi : le serveur remet les clichés dans l'ordre chronologique
    r = client.put("/api/radiograph-comparisons", headers=h,
                   json={"document_a_id": new, "document_b_id": old, "qualification": "amelioration",
                         "comment": "Nette régression"})
    assert r.status_code == 200 and r.json()["document_a_id"] == old
    r = client.put("/api/radiograph-comparisons", headers=h,
                   json={"document_a_id": old, "document_b_id": new, "qualification": "stable"})
    assert r.json()["qualification"] == "stable"
    assert len(client.get(f"/api/patients/{pid}/radiograph-comparisons", headers=h).json()) == 1
    f = client.get(f"/api/patients/{pid}/facts?as_of=2026-06-01", headers=h).json()
    assert f["radiographs"]["doctor_qualification"]["qualification"] == "stable"
    sheet = client.post(f"/api/patients/{pid}/sheets?as_of=2026-06-01", headers=h).json()
    assert "Évolution jugée par le médecin : stabilité" in sheet["html"]
    make_user(db, "x@demo.ma")
    assert client.put("/api/radiograph-comparisons", headers=login(client, "x@demo.ma"),
                      json={"document_a_id": old, "document_b_id": new, "qualification": "stable"}).status_code == 404


def test_registration_recovers_a_known_rotation(tmp_path):
    from app.services import registration

    rng = np.random.default_rng(0)
    base = np.zeros((600, 600), np.uint8)
    base[100:500, 80:270] = 160   # deux « champs pulmonaires » et du bruit de texture
    base[100:500, 330:520] = 160
    base = np.clip(base + rng.normal(0, 25, base.shape), 0, 255).astype(np.uint8)
    a = Image.fromarray(base)
    b = a.rotate(5, resample=Image.BILINEAR, translate=(12, -8))
    a.save(tmp_path / "a.png")
    b.save(tmp_path / "b.png")
    r = registration.register(tmp_path / "a.png", tmp_path / "b.png")
    assert abs(abs(r.angle) - 5) <= 0.5 and r.ncc_after > r.ncc_before and r.png.startswith(b"\x89PNG")


def test_difference_map_endpoint_is_cached_and_isolated(client, db, fake_model):
    h, pid = setup(client, db)
    old = upload_xray(client, h, pid, xray_png(), "r1.png", "2026-02-11")
    new = upload_xray(client, h, pid, xray_png((820, 800)), "r2.png", "2026-05-15")
    info = client.get(f"/api/documents/{new}/difference/{old}", headers=h).json()
    assert info["older"] == old and info["newer"] == new and "reliable" in info  # ordre chronologique rétabli
    img = client.get(f"/api/documents/{old}/difference/{new}/image", headers=h)
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    make_user(db, "y@demo.ma")
    assert client.get(f"/api/documents/{old}/difference/{new}", headers=login(client, "y@demo.ma")).status_code == 404
