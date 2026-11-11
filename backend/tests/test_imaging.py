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
