"""Analyse des radiographies thoraciques (F-C2, F-C3).

- Modèle : TorchXRayVision DenseNet121 `densenet121-res224-all` (modèle de recherche pré-entraîné, CPU).
  Il produit une probabilité calibrée par pathologie (0,5 = seuil de fonctionnement du modèle).
- Incertitude : écart-type des scores sur 7 variantes légèrement modifiées de l'image (rotation, décalage,
  contraste) ; un score instable signale une lecture fragile.
- Grad-CAM : zone de l'image qui a le plus pesé dans le score d'une pathologie. Ce n'est PAS une
  localisation de lésion (garde-fou n° 6).
- Contrôles de qualité : taille, couleur, proportions, contraste. Une image suspecte est analysée mais
  signalée ; une vue de profil déclarée par le médecin est exclue des comparaisons.
Les scores ne constituent pas un diagnostic.
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_NAME = "densenet121-res224-all"
# Pathologies affichées (le modèle en produit 18 ; on garde celles utiles au suivi pneumologique)
SHOWN = ["Consolidation", "Pneumonia", "Lung Opacity", "Infiltration", "Effusion", "Atelectasis", "Emphysema",
         "Fibrosis", "Edema", "Cardiomegaly"]
TTA = [  # (rotation en degrés, décalage x, décalage y, facteur de contraste)
    (0, 0, 0, 1.0), (-4, 0, 0, 1.0), (4, 0, 0, 1.0), (0, 8, 0, 1.0), (0, 0, -8, 1.0), (0, 0, 0, 0.9), (0, 0, 0, 1.1)]


@dataclass
class XrayResult:
    scores: dict[str, float]
    uncertainty: dict[str, float]
    quality_flags: list[str] = field(default_factory=list)
    model_name: str = MODEL_NAME
    model_version: str = ""


class XrayModel:
    """Modèle chargé une seule fois (singleton paresseux), protégé par un verrou pour les tâches concurrentes."""

    _instance: XrayModel | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        import torch
        import torchxrayvision as xrv
        self.torch, self.xrv = torch, xrv
        self.model = xrv.models.DenseNet(weights=MODEL_NAME)
        self.model.eval()
        self.pathologies = [p for p in self.model.pathologies]
        self.version = f"torchxrayvision {xrv.__version__}"
        self.run_lock = threading.Lock()

    @classmethod
    def get(cls) -> XrayModel:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def loaded(cls) -> bool:
        return cls._instance is not None

    # ------------------------------------------------------------ prétraitement
    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """Image en niveaux de gris [0, 255] -> tableau 224x224 normalisé (chaîne officielle TorchXRayVision :
        normalisation [-1024, 1024], recadrage central carré, redimensionnement). Fait UNE fois par image."""
        x = self.xrv.datasets.normalize(img.astype(np.float32), 255)[None]
        x = self.xrv.datasets.XRayCenterCrop()(x)
        x = self.xrv.datasets.XRayResizer(224, engine="cv2" if _has_cv2() else "skimage")(x)
        return x[0].astype(np.float32)

    def to_tensor(self, x224: np.ndarray):
        return self.torch.from_numpy(np.ascontiguousarray(x224, dtype=np.float32))[None, None]

    def scores(self, x) -> np.ndarray:
        with self.run_lock, self.torch.no_grad():
            return self.model(x)[0].numpy()

    def gradcam(self, x, pathology: str) -> np.ndarray:
        """Carte 224x224 dans [0, 1] pour une pathologie."""
        idx = self.pathologies.index(pathology)
        F = self.torch.nn.functional
        # Fin du calcul du modèle refaite à la main : la version d'origine (features2) applique un ReLU
        # « en place » sur les activations, ce qui empêche de récupérer leur gradient.
        with self.run_lock:
            act = self.model.features(x)
            act.retain_grad()
            pooled = F.adaptive_avg_pool2d(F.relu(act), (1, 1)).flatten(1)
            out = self.torch.sigmoid(self.model.classifier(pooled))
            if getattr(self.model, "op_threshs", None) is not None:
                out = self.xrv.models.op_norm(out, self.model.op_threshs)
            self.model.zero_grad()
            out[0, idx].backward()
            grad = act.grad[0].detach()
            act = act[0].detach()
        weights = grad.mean(dim=(1, 2))
        cam = self.torch.relu((weights[:, None, None] * act).sum(0)).numpy()
        if cam.max() > 0:
            cam = cam / cam.max()
        return np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize((224, 224), Image.BILINEAR),
                          dtype=np.float32) / 255


def _has_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------- fonctions de service
def load_gray(path: Path) -> tuple[np.ndarray, list[str]]:
    img = Image.open(path)
    flags = []
    if img.mode in ("RGB", "RGBA"):
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
        if np.abs(rgb - rgb.mean(axis=2, keepdims=True)).mean() > 8:
            flags.append("couleur")  # une radiographie est en niveaux de gris
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = gray.shape
    if min(h, w) < 512:
        flags.append("resolution_faible")
    if not 0.7 <= w / h <= 1.45:
        flags.append("proportions_inhabituelles")
    if gray.std() < 25:
        flags.append("contraste_faible")
    return gray, flags


def _variant(x224: np.ndarray, rot: float, dx: int, dy: int, contrast: float) -> np.ndarray:
    """Variante légère de l'image déjà prétraitée (224x224, valeurs [-1024, 1024]) ; fond = noir (-1024)."""
    img = Image.fromarray(x224, mode="F")
    if rot:
        img = img.rotate(rot, resample=Image.BILINEAR, fillcolor=-1024.0)
    if dx or dy:
        img = img.transform(img.size, Image.AFFINE, (1, 0, dx * 224 / 1024, 0, 1, dy * 224 / 1024), fillcolor=-1024.0)
    arr = np.asarray(img, dtype=np.float32)
    if contrast != 1.0:
        arr = np.clip((arr - arr.mean()) * contrast + arr.mean(), -1024, 1024)
    return arr


def analyze(path: Path, model: XrayModel | None = None) -> XrayResult:
    model = model or XrayModel.get()
    gray, flags = load_gray(path)
    base = model.preprocess(gray)
    runs = np.stack([model.scores(model.to_tensor(_variant(base, *v))) for v in TTA])
    mean, std = runs.mean(axis=0), runs.std(axis=0)
    by = dict(zip(model.pathologies, range(len(model.pathologies)), strict=True))
    return XrayResult({p: round(float(mean[by[p]]), 4) for p in SHOWN if p in by},
                      {p: round(float(std[by[p]]), 4) for p in SHOWN if p in by}, flags, MODEL_NAME, model.version)


# Palette séquentielle (bleu nuit -> sarcelle -> jaune), transparente pour les valeurs faibles
_STOPS = np.array([[0.00, 20, 30, 70], [0.45, 14, 107, 107], [0.75, 120, 190, 120], [1.00, 250, 230, 90]], dtype=np.float32)


def gradcam_overlay(path: Path, pathology: str, model: XrayModel | None = None) -> bytes:
    """PNG RGBA de la taille de l'image d'origine : carte posée sur le carré central analysé par le modèle."""
    model = model or XrayModel.get()
    gray, _ = load_gray(path)
    cam = model.gradcam(model.to_tensor(model.preprocess(gray)), pathology)
    h, w = gray.shape
    side = min(h, w)
    cam_img = np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize((side, side), Image.BILINEAR),
                         dtype=np.float32) / 255
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    top, left = (h - side) // 2, (w - side) // 2
    color = np.stack([np.interp(cam_img, _STOPS[:, 0], _STOPS[:, k]) for k in (1, 2, 3)], axis=-1)
    alpha = np.clip((cam_img - 0.25) / 0.75, 0, 1) * 190  # sous 25 % : transparent
    rgba[top:top + side, left:left + side, :3] = color.astype(np.uint8)
    rgba[top:top + side, left:left + side, 3] = alpha.astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- base de données
def run_analysis(db, doc):
    """Analyse (ou ré-analyse) la radiographie d'un document et enregistre le résultat dans `imaging`."""
    from sqlalchemy import select

    from app.db.models import Imaging
    from app.services import storage

    res = analyze(storage.absolute(doc.file_path))
    im = db.scalar(select(Imaging).where(Imaging.document_id == doc.id))
    if im is None:
        im = Imaging(document_id=doc.id, date=doc.exam_date or doc.created_at.date(), view="face")
        db.add(im)
    im.date = doc.exam_date or im.date
    im.scores, im.uncertainty = res.scores, res.uncertainty
    im.quality_flag = ",".join(res.quality_flags) or None
    im.model_name, im.model_version = res.model_name, res.model_version
    for f in storage.absolute(doc.file_path).parent.glob(f"{doc.id}.cam.*.png"):
        f.unlink()  # cartes Grad-CAM d'une analyse précédente
    return im
