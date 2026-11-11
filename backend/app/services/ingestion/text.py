"""Extraction du texte avec positions (F-A4).

- PDF natif : mots et boîtes via PyMuPDF (confiance 1).
- Scan (PDF image) ou photo : redressement automatique, puis Tesseract `fra` (confiance par mot).
Toutes les boîtes sont en coordonnées normalisées [0, 1] de la page, ce qui permet au frontend de les
superposer à l'aperçu quelle que soit sa taille.
"""
from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median

import numpy as np
import pymupdf
import pytesseract
from PIL import Image, ImageFilter, ImageOps

from app.core.config import get_settings

OCR_DPI = 300
MIN_NATIVE_CHARS = 40  # en dessous, la page est considérée comme une image


@dataclass
class Word:
    text: str
    conf: float
    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def page(self) -> int:
        return self.words[0].page

    @property
    def conf(self) -> float:
        return min(w.conf for w in self.words)

    def bbox(self, words: list[Word] | None = None) -> dict:
        ws = words or self.words
        return {"page": ws[0].page, "x0": min(w.x0 for w in ws), "y0": min(w.y0 for w in ws),
                "x1": max(w.x1 for w in ws), "y1": max(w.y1 for w in ws)}


@dataclass
class PageText:
    number: int
    width: float
    height: float
    ocr: bool
    words: list[Word] = field(default_factory=list)


@dataclass
class DocumentText:
    pages: list[PageText]
    is_image: bool  # fichier image (photo/radiographie) et non PDF

    @property
    def words(self) -> list[Word]:
        return [w for p in self.pages for w in p.words]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in group_lines(self.words))

    @property
    def ocr(self) -> bool:
        return any(p.ocr for p in self.pages)

    @property
    def mean_conf(self) -> float:
        ws = self.words
        return float(np.mean([w.conf for w in ws])) if ws else 0.0

    def boxes_json(self) -> dict:
        return {"pages": [{"number": p.number, "width": p.width, "height": p.height, "ocr": p.ocr} for p in self.pages],
                "words": [asdict(w) for w in self.words]}


# ---------------------------------------------------------------- OCR
def otsu_threshold(arr: np.ndarray) -> int:
    hist = np.bincount(arr.ravel(), minlength=256).astype(np.float64)
    w = np.cumsum(hist)
    m = np.cumsum(hist * np.arange(256))
    total_w, total_m = w[-1], m[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (total_m * w - m * total_w) ** 2 / (w * (total_w - w))
    between[~np.isfinite(between)] = 0
    return int(np.argmax(between))


def binarize(gray: Image.Image) -> Image.Image:
    """Filtre médian (bruit de scan) puis seuil d'Otsu. Mesuré sur les scans synthétiques : 9/9 valeurs
    retrouvées contre 1/9 sans prétraitement, et OCR 3 fois plus rapide."""
    arr = np.asarray(gray.filter(ImageFilter.MedianFilter(3)), dtype=np.uint8)
    return Image.fromarray(((arr > otsu_threshold(arr)) * 255).astype(np.uint8))


def estimate_skew(gray: Image.Image, max_angle: float = 3.0, step: float = 0.25) -> float:
    """Angle (degrés) qui maximise la variance du profil horizontal de l'image binarisée."""
    small = gray.copy()
    small.thumbnail((900, 900))
    arr = np.asarray(small, dtype=np.uint8)
    ink = Image.fromarray(((arr < 160) * 255).astype(np.uint8))
    best, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step / 2, step):
        rot = np.asarray(ink.rotate(float(angle), resample=Image.NEAREST, fillcolor=0), dtype=np.float32)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best, best_score = float(angle), score
    return best


def ocr_image(img: Image.Image, page: int) -> PageText:
    gray = ImageOps.autocontrast(ImageOps.exif_transpose(img).convert("L"))
    angle = estimate_skew(gray)
    if abs(angle) >= 0.25:
        gray = gray.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    if gray.width < 1600:  # les photos basse résolution sont agrandies pour Tesseract
        f = 1600 / gray.width
        gray = gray.resize((int(gray.width * f), int(gray.height * f)), Image.LANCZOS)
    gray = binarize(gray)
    pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd
    data = pytesseract.image_to_data(gray, lang="fra", config="--psm 6", output_type=pytesseract.Output.DICT)
    W, H = gray.width, gray.height
    words = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(txt, conf / 100, page, x / W, y / H, (x + w) / W, (y + h) / H))
    return PageText(page, W, H, True, words)


# ---------------------------------------------------------------- lecture des fichiers
def extract_pdf(data: bytes) -> DocumentText:
    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for i, pg in enumerate(doc):
            W, H = pg.rect.width, pg.rect.height
            raw = pg.get_text("words")
            if sum(len(w[4]) for w in raw) >= MIN_NATIVE_CHARS:
                words = [Word(w[4], 1.0, i, w[0] / W, w[1] / H, w[2] / W, w[3] / H) for w in raw]
                pages.append(PageText(i, W, H, False, words))
            else:
                pix = pg.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY)
                img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                pages.append(ocr_image(img, i))
    return DocumentText(pages, is_image=False)


def extract_image(data: bytes) -> DocumentText:
    img = Image.open(io.BytesIO(data))
    return DocumentText([ocr_image(img, 0)], is_image=True)


def extract(path: Path, mime: str) -> DocumentText:
    data = path.read_bytes()
    return extract_pdf(data) if mime == "application/pdf" else extract_image(data)


# ---------------------------------------------------------------- lignes visuelles
def group_lines(words: list[Word]) -> list[Line]:
    """Regroupe les mots en lignes par recouvrement vertical (gère les tableaux dont les cellules sont
    dans des blocs différents). Les lignes sont triées de haut en bas, les mots de gauche à droite."""
    lines: list[Line] = []
    for page in sorted({w.page for w in words}):
        ws = sorted((w for w in words if w.page == page), key=lambda w: w.yc)
        if not ws:
            continue
        h = median(w.y1 - w.y0 for w in ws) or 0.01
        current: list[Word] = [ws[0]]
        for w in ws[1:]:
            ref = sum(x.yc for x in current) / len(current)
            if abs(w.yc - ref) <= 0.5 * h:
                current.append(w)
            else:
                lines.append(Line(sorted(current, key=lambda x: x.x0)))
                current = [w]
        lines.append(Line(sorted(current, key=lambda x: x.x0)))
    return lines
