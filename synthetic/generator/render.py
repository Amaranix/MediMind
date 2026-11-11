"""Rendu HTML -> PDF (Chromium via Playwright) et dégradation en « scans » (photo JPG ou PDF image)."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageEnhance, ImageFilter


class PdfRenderer:
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page()
        return self

    def render(self, html: str, out: Path) -> None:
        self._page.set_content(html, wait_until="load")
        self._page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()


def degrade(pdf: Path, rng: np.random.Generator, as_photo: bool) -> Path:
    """Transforme un PDF natif en scan : rotation (±1,5°), flou, bruit, contraste, compression JPEG.

    as_photo=True -> fichier .jpg (photo de document) ; sinon PDF ne contenant qu'une image (scanner).
    Le PDF natif d'origine est supprimé.
    """
    doc = pymupdf.open(pdf)
    pix = doc[0].get_pixmap(dpi=int(rng.integers(150, 201)), colorspace=pymupdf.csGRAY)
    doc.close()
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    img = img.rotate(float(rng.uniform(-1.5, 1.5)), resample=Image.BICUBIC, expand=True, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.4, 1.1))))
    arr = np.asarray(img, dtype=np.float32)
    arr += rng.normal(0, rng.uniform(6, 14), arr.shape)
    if as_photo:  # éclairage inégal d'une photo de téléphone
        h, w = arr.shape
        grad = np.linspace(rng.uniform(-25, 0), rng.uniform(0, 15), w)[None, :]
        arr += grad
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img = ImageEnhance.Contrast(img).enhance(float(rng.uniform(0.8, 1.15)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=int(rng.integers(55, 81)))
    pdf.unlink()
    if as_photo:
        out = pdf.with_suffix(".jpg")
        out.write_bytes(buf.getvalue())
        return out
    out = pdf
    d = pymupdf.open()
    w_pt, h_pt = 595, 842
    pg = d.new_page(width=w_pt, height=h_pt)
    pg.insert_image(pg.rect, stream=buf.getvalue(), keep_proportion=True)
    d.save(out)
    d.close()
    return out
