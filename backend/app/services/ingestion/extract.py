"""Extraction structurée par règles (F-A6), prioritaire sur le LLM.

- Bilans biologiques : ligne visuelle = libellé, valeur, unité (dans n'importe quel ordre unité/valeur).
- EFR : colonnes repérées par l'en-tête (Théorique, Pré-BD, Post-BD, Mesuré, % Théo), valeurs affectées
  à la colonne la plus proche en abscisse.
- Comptes rendus : expressions régulières (SpO2 et contexte, gaz du sang).
Chaque valeur garde sa boîte (page + coordonnées) et le texte source, pour l'écran de validation.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from app.services.ingestion.normalize import (
    LabelMatcher,
    fold,
    infer_unit_by_magnitude,
    is_plausible,
    parse_number,
    resolve_unit,
)
from app.services.ingestion.text import DocumentText, Line, Word, group_lines
from app.services.referential import Referential

LAB_CODES = {"WBC", "NEUT", "LYMPH", "EOS", "HB", "PLT", "CRP", "PCT", "CREAT"}
EFR_CODES = {"FEV1", "FVC", "FEV1_FVC"}


@dataclass
class ExtractedValue:
    param: str
    value: float              # valeur canonique (unité du référentiel)
    unit: str                 # unité canonique
    printed_value: float      # valeur telle qu'imprimée
    printed_unit: str | None  # unité reconnue sur le document
    context: list[str]
    confidence: float
    bbox: dict | None
    source_text: str
    flags: list[str] = field(default_factory=list)

    @property
    def suspect(self) -> bool:
        return "implausible" in self.flags


def _finish(ref: Referential, code: str, printed: float, raw_unit: str | None, context: list[str], conf: float,
            bbox: dict | None, source: str, flags: list[str]) -> ExtractedValue | None:
    p = ref.parameter(code)
    unit, factor, score = resolve_unit(p, raw_unit)
    if unit is None:
        guess = infer_unit_by_magnitude(p, printed)
        if guess is None:
            unit, factor = p.unit, 1.0
            flags.append("unit_unknown")
            conf = min(conf, 0.5)
        else:
            unit, factor = guess
            flags.append("unit_inferred")
            conf = min(conf, 0.7)
    elif score < 100:
        flags.append("unit_fuzzy")
        conf *= 0.95
    if "ocr" in flags:
        conf = min(conf, OCR_CONF_CAP)
    canonical = round(printed * factor, 6)
    if not is_plausible(p, canonical):
        flags.append("implausible")
        conf = min(conf, 0.4)
    return ExtractedValue(code, canonical, p.unit, printed, unit, context, round(conf, 3), bbox, source, flags)


# ---------------------------------------------------------------- bilans biologiques
RANGE_SEPARATORS = {"-", "–", "—", "à", "a"}
OCR_CONF_CAP = 0.9  # une valeur lue par OCR n'est jamais assez sûre pour une validation groupée


def _in_reference(words: list[Word], i: int) -> bool:
    """Nombre appartenant à une plage de référence : entre parenthèses « (150 - 400) », ou de part et d'autre
    d'un séparateur « 4,0 - 10,0 », « 4 000 à 10 000 »."""
    depth = 0
    for w in words[:i]:
        depth += w.text.count("(") - w.text.count(")")
    if depth > 0 or words[i].text.lstrip().startswith("("):
        return True
    prev = words[i - 1].text.strip() if i > 0 else ""
    nxt = words[i + 1].text.strip() if i + 1 < len(words) else ""
    after = words[i + 2].text if i + 2 < len(words) else ""
    return prev in RANGE_SEPARATORS or (nxt in RANGE_SEPARATORS and parse_number(after.strip("()")) is not None)


def extract_lab(doc: DocumentText, ref: Referential) -> list[ExtractedValue]:
    matcher = LabelMatcher(ref, LAB_CODES)
    out: dict[str, ExtractedValue] = {}
    for line in group_lines(doc.words):
        m = matcher.match_prefix([w.text for w in line.words[:5]])
        if not m or m.code in out:
            continue
        p = ref.parameter(m.code)
        rest = line.words[m.n_words:]
        unit_before: str | None = None
        value_idx = None
        parsed = None
        for i, w in enumerate(rest):
            parsed = parse_number(w.text, allow_ocr_fix=doc.ocr)
            if parsed and not _in_reference(rest, i):
                value_idx = i
                break
            parsed = None
            u, _, score = resolve_unit(p, w.text)
            if u and score >= 80:
                unit_before = w.text
        if value_idx is None or parsed is None:
            continue
        value, ocr_fixed = parsed
        vw = [rest[value_idx]]
        j = value_idx + 1
        # Séparateur de milliers lu comme un espace : « 12 400 /mm³ »
        # (fusion seulement si une unité suit : « 141 120 - 170 » est une valeur suivie d'une plage)
        if (j + 1 < len(rest) and value.is_integer() and value < 1000 and re.fullmatch(r"\d{3}", rest[j].text)
                and (resolve_unit(p, rest[j + 1].text)[2] >= 80)):
            value = value * 1000 + float(rest[j].text)
            vw.append(rest[j])
            j += 1
        raw_unit = None
        if j < len(rest):
            raw_unit = rest[j].text
            u, _, score = resolve_unit(p, raw_unit)
            if (u is None or score < 60) and j + 1 < len(rest):
                joined = rest[j].text + rest[j + 1].text
                if resolve_unit(p, joined)[0]:
                    raw_unit = joined
        if (raw_unit is None or resolve_unit(p, raw_unit)[0] is None) and unit_before:
            raw_unit = unit_before
        label_words = line.words[:m.n_words]
        conf = 0.97 if not doc.ocr else min(w.conf for w in label_words + vw)
        conf = max(conf, 0.3)
        flags = ["ocr"] if doc.ocr else []
        if m.score < 100:
            flags.append("label_fuzzy")
            conf *= m.score / 100
        if ocr_fixed:
            flags.append("ocr_digit_fix")
            conf = min(conf, 0.6)
        ev = _finish(ref, m.code, value, raw_unit, [], conf, line.bbox(label_words + vw), line.text, flags)
        if ev:
            out[m.code] = ev
    return list(out.values())


# ---------------------------------------------------------------- EFR
def _efr_columns(lines: list[Line]) -> tuple[int, dict[str, float]] | None:
    """Repère la ligne d'en-tête et l'abscisse du centre de chaque colonne."""
    for idx, line in enumerate(lines):
        f = [fold(w.text) for w in line.words]
        if not any(x.startswith("theori") for x in f):
            continue
        cols: dict[str, float] = {}
        for k, w in enumerate(line.words):
            x = (w.x0 + w.x1) / 2
            t = f[k]
            if t.startswith("theori") and "theo" not in cols:
                cols["theo"] = x
            elif t.startswith("pre"):
                cols["pre"] = x
            elif t.startswith("post") and not w.text.startswith("("):
                cols["post"] = x
            elif t.startswith("mesur"):
                cols["mesure"] = x
            elif t == "%" or t.startswith("%"):
                nxt = line.words[k + 1] if k + 1 < len(line.words) else w
                cols["pct"] = (w.x0 + nxt.x1) / 2
        if "post" in cols or "mesure" in cols:
            return idx, cols
    return None


def _efr_without_header(doc: DocumentText, lines: list[Line], matcher: LabelMatcher,
                        ref: Referential) -> list[ExtractedValue]:
    """En-tête illisible (scan) : colonnes déduites du nombre de valeurs sur la ligne. Confiance plafonnée."""
    text = fold(doc.text)
    bd = any(k in text for k in ("pre bd", "post bd", "reversibilite"))
    layouts = ({4: ["theo", "pre", "post", "pct"], 2: ["pre", "post"], 1: ["post"]} if bd
               else {3: ["theo", "post", "pct"], 2: ["theo", "post"], 1: ["post"]})
    main_ctx = ["post_bd"] if bd else []
    out = []
    for line in lines:
        m = matcher.match_prefix([w.text for w in line.words[:3]])
        if not m or m.score < 100:
            continue
        rest = line.words[m.n_words:]
        nums = [(w, p) for w in rest if (p := parse_number(w.text, allow_ocr_fix=doc.ocr))]
        unit_tok = next((w.text for w in rest if parse_number(w.text) is None and w.text.strip()), None)
        if m.code == "FEV1_FVC" and len(nums) == 2 and not bd:
            continue
        cols = layouts.get(len(nums))
        if not cols:
            continue
        for (w, parsed), col in zip(nums, cols, strict=True):
            if col == "theo":
                continue
            conf = min(0.8, max(w.conf, 0.3))
            flags = ["columns_inferred"] + (["ocr"] if doc.ocr else []) + (["ocr_digit_fix"] if parsed[1] else [])
            if col == "pct":
                code = {"FEV1": "FEV1_PRED", "FVC": "FVC_PRED"}.get(m.code)
                if code:
                    out.append(_finish(ref, code, parsed[0], "%", main_ctx, conf, line.bbox([w]), line.text, flags))
                continue
            ctx = ["pre_bd"] if col == "pre" else list(main_ctx)
            out.append(_finish(ref, m.code, parsed[0], unit_tok, ctx, conf, line.bbox([w]), line.text, flags))
    return out


def extract_efr(doc: DocumentText, ref: Referential) -> list[ExtractedValue]:
    lines = group_lines(doc.words)
    out: list[ExtractedValue] = []
    header = _efr_columns(lines)
    matcher = LabelMatcher(ref, EFR_CODES)
    if header:
        h_idx, cols = header
        bd = "pre" in cols
        main_ctx = ["post_bd"] if bd else []
        for line in lines[h_idx + 1:]:
            m = matcher.match_prefix([w.text for w in line.words[:3]])
            if not m or m.score < 100:
                continue
            rest = line.words[m.n_words:]
            unit_tok = next((w.text for w in rest if parse_number(w.text) is None and w.text.strip()), None)
            for w in rest:
                parsed = parse_number(w.text, allow_ocr_fix=doc.ocr)
                if not parsed:
                    continue
                x = (w.x0 + w.x1) / 2
                col = min(cols, key=lambda c: abs(cols[c] - x))
                conf = 0.97 if not doc.ocr else max(min(w.conf, *(x.conf for x in line.words[:m.n_words])), 0.3)
                flags = (["ocr"] if doc.ocr else []) + (["ocr_digit_fix"] if parsed[1] else [])
                if col == "theo":
                    continue
                if col == "pct":
                    code = {"FEV1": "FEV1_PRED", "FVC": "FVC_PRED"}.get(m.code)
                    if code:
                        ev = _finish(ref, code, parsed[0], "%", main_ctx, conf, line.bbox([w]), line.text, flags)
                        out.append(ev)
                    continue
                ctx = ["pre_bd"] if col == "pre" else main_ctx
                ev = _finish(ref, m.code, parsed[0], unit_tok, list(ctx), conf, line.bbox([w]), line.text, flags)
                out.append(ev)
    else:
        out += _efr_without_header(doc, lines, matcher, ref)
    # DLCO dans le texte libre : « DLCO à 51 % de la valeur théorique »
    for line in lines:
        f = fold(line.text)
        mm = re.search(r"dlco\D{0,20}?(\d{1,3}(?:[.,]\d)?)\s*%", f)
        if mm:
            num_word = next((w for w in line.words if parse_number(w.text) and
                             parse_number(w.text)[0] == float(mm.group(1).replace(",", "."))), None)
            conf = 0.97 if not doc.ocr else (num_word.conf if num_word else 0.5)
            out.append(_finish(ref, "DLCO_PRED", float(mm.group(1).replace(",", ".")), "%", [], max(conf, 0.3),
                               line.bbox([num_word]) if num_word else line.bbox(), line.text,
                               ["ocr"] if doc.ocr else []))
            break
    return [v for v in out if v]


# ---------------------------------------------------------------- comptes rendus
class TextIndex:
    """Texte continu du document avec correspondance caractère -> mot (pour les expressions régulières
    qui traversent les retours à la ligne)."""

    def __init__(self, words: list[Word]):
        self.words: list[Word] = []
        self.starts: list[int] = []
        parts: list[str] = []
        pos = 0
        for line in group_lines(words):
            for w in line.words:
                self.words.append(w)
                self.starts.append(pos)
                parts.append(w.text)
                pos += len(w.text) + 1
        self.text = " ".join(parts)

    def words_in(self, start: int, end: int) -> list[Word]:
        return [w for w, s in zip(self.words, self.starts, strict=True) if s < end and s + len(w.text) > start]

    def bbox(self, start: int, end: int) -> dict | None:
        ws = self.words_in(start, end)
        if not ws:
            return None
        ws = [w for w in ws if w.page == ws[0].page]
        return {"page": ws[0].page, "x0": min(w.x0 for w in ws), "y0": min(w.y0 for w in ws),
                "x1": max(w.x1 for w in ws), "y1": max(w.y1 for w in ws)}

    def conf(self, start: int, end: int) -> float:
        ws = self.words_in(start, end)
        return min((w.conf for w in ws), default=0.5)


NUM = r"(\d+(?:[.,]\d+)?)"
CR_PATTERNS = [
    ("SPO2", re.compile(r"Sp\s?O\s?[2₂]\s*(?:à|a|:|=|de)?\s*" + NUM + r"\s*%", re.I), "%"),
    ("PH", re.compile(r"\bpH\s*(?:à|:|=)?\s*(\d[.,]\d{1,2})\b"), "pH"),
    ("PAO2", re.compile(r"Pa\s?O\s?2\s*(?:à|:|=)?\s*" + NUM + r"\s*(mmHg|kPa)", re.I), None),
    ("PACO2", re.compile(r"Pa\s?CO\s?2\s*(?:à|:|=)?\s*" + NUM + r"\s*(mmHg|kPa)", re.I), None),
    ("HCO3", re.compile(r"HCO3\s*-?\s*(?:à|:|=)?\s*" + NUM + r"\s*(mmol/L|mEq/L)", re.I), None),
]


def _context(snippet: str) -> list[str]:
    f = fold(snippet)
    ctx = []
    if "repos" in f:
        ctx.append("rest")
    if "effort" in f:
        ctx.append("exercise")
    if "air ambiant" in f:
        ctx.append("room_air")
    if re.search(r"sous (o2|oxyg|\d+ ?l)", f):
        ctx.append("oxygen")
    return ctx


def extract_report(doc: DocumentText, ref: Referential) -> list[ExtractedValue]:
    idx = TextIndex(doc.words)
    out: dict[str, ExtractedValue] = {}
    gds_pos = idx.text.lower().find("gaz du sang")
    gds_context = [c for c in _context(idx.text[gds_pos:gds_pos + 200]) if c in ("room_air", "oxygen")] \
        if gds_pos >= 0 else []
    for code, rx, fixed_unit in CR_PATTERNS:
        m = rx.search(idx.text)
        if not m or code in out:
            continue
        value = float(m.group(1).replace(",", "."))
        unit = fixed_unit or m.group(2)
        ctx = _context(idx.text[m.end(): m.end() + 60]) if code == "SPO2" else list(gds_context)
        conf = 0.95 if not doc.ocr else max(idx.conf(m.start(1), m.end(1)), 0.3)
        ev = _finish(ref, code, value, unit, ctx, conf, idx.bbox(m.start(), m.end()), m.group(0),
                     ["ocr"] if doc.ocr else [])
        if ev:
            out[code] = ev
    return list(out.values())


# ---------------------------------------------------------------- date de l'examen
DATE = r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"
DATE_PATTERNS = [
    re.compile(r"Pr[ée]l[èe]v(?:ement|é)\s*(?:du|le)?\s*" + DATE, re.I),
    re.compile(r"respiratoire\s+du\s+" + DATE, re.I),
    re.compile(r"(?:^|\s)Le\s+" + DATE),
    re.compile(r",\s*le\s+" + DATE, re.I),
]
BIRTH = re.compile(r"n[ée]\s*\(?e?\)?\s*le\s+" + DATE, re.I)


def _to_date(m: re.Match, offset: int = 0) -> dt.date | None:
    try:
        return dt.date(int(m.group(3 + offset)), int(m.group(2 + offset)), int(m.group(1 + offset)))
    except ValueError:
        return None


def find_exam_date(doc: DocumentText) -> dt.date | None:
    text = TextIndex(doc.words).text
    births = {_to_date(m) for m in BIRTH.finditer(text)}
    for rx in DATE_PATTERNS:
        for m in rx.finditer(text):
            d = _to_date(m)
            if d and d not in births and dt.date(1990, 1, 1) <= d <= dt.date.today():
                return d
    candidates = [d for m in re.finditer(DATE, text) if (d := _to_date(m)) and d not in births
                  and dt.date(1990, 1, 1) <= d <= dt.date.today()]
    return max(set(candidates), key=candidates.count) if candidates else None
