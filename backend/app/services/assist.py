"""Rédaction assistée de la fiche (F-E2, étapes 2-3) : le LLM local reformule, le code vérifie.

1. `digest` : les faits saillants mis en phrases courtes par le code (nombres déjà formatés à la française).
   C'est la seule entrée du LLM : pas de nom, pas d'identifiant. Seuls les paramètres hors zone, en tendance
   non stable ou visés par une alerte y figurent (entrée courte : le modèle tourne sur CPU).
2. `verify` : contrôles déterministes du texte produit, contre le digest :
   - nombres et dates : chacun doit figurer dans le digest (tolérance : arrondi à la précision écrite) ;
   - unité : un nombre suivi d'une unité (ans, %, L, mg/L...) doit apparaître avec cette unité dans le digest
     (« 40 ans » est refusé si le digest dit « 40 paquets-années ») ;
   - tendances : une phrase qui qualifie un paramètre (dégradation, amélioration, stable) doit concorder avec
     la tendance calculée ;
   - radiographies : variation dans la marge d'incertitude => pas d'« augmentation » ni de « diminution » ;
   - mots interdits (« diagnostic », « certain », « souffre »...) et maladies absentes du digest.
   Limite : le sens général d'une phrase n'est pas vérifiable par règles ; le texte reste signalé comme
   rédigé par un LLM et le médecin dispose toujours de la fiche gabarit.
3. `draft` : 2 tentatives au plus ; sinon None, l'appelant revient au gabarit (« rédaction assistée indisponible »).
"""
from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata

from app.services import llm
from app.services.sheet import CONTEXTS, EVENTS, PATHOLOGIES, TRENDS, fdate, fnum

MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre",
          "novembre", "decembre"]
FORBIDDEN = [r"diagnosti\w*", r"certainement", r"certaines?", r"certain", r"certitude", r"souffr\w*", r"atteint",
             r"je recommande", r"il faut", r"il convient", r"doit etre (?:traite|prescrit|arrete)", r"significati\w*",
             r"fume", r"fumeur", r"inquietant\w*", r"grave", r"severe"]
CTX = r"(?: post-bd| pre-bd| repos air ambiant| repos| air ambiant)?"  # contexte de mesure dans le digest
ACRONYMS = r"(?:vems|cvf|dlco|crp|spo2|bpco|post-bd|pre-bd|pct|efr)"
DISEASES = ["bpco", "asthme", "fibrose", "pneumonie", "pneumopathie", "cancer", "tumeur", "carcinome", "tuberculose",
            "embolie", "covid", "emphyseme", "sarcoidose", "mucoviscidose", "bronchectasie", "dilatation des bronches",
            "insuffisance cardiaque", "insuffisance respiratoire", "hypertension pulmonaire", "pleuresie",
            "pneumothorax", "oedeme", "sepsis", "grippe", "bronchite"]
UNITS = ["paquets-annees", "ans", "an", "%", "l", "ml", "mg/l", "g/l", "g/dl", "ng/ml", "mmhg", "mmol/l", "jours",
         "mois", "points", "pts"]
QUALIF = {"degradation": "worsening", "degrade": "worsening", "degradee": "worsening", "aggravation": "worsening",
          "declin": "worsening", "amelioration": "improving", "ameliore": "improving", "amelioree": "improving",
          "stable": "stable", "stabilite": "stable"}
MOVE = re.compile(r"\b(augment\w*|diminu\w*|hausse|baisse|progress\w*|regress\w*|aggrav\w*|amelior\w*)\b")
MAX_ATTEMPTS = 2

DATE_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
DATE_WORDS = re.compile(r"\b(?:(\d{1,2})(?:er)?\s+)?(" + "|".join(MONTHS) + r")\s+(\d{4})\b")
NUMBER = re.compile(r"(?<![\w.,/])[-−+]?\d+(?:[.,]\d+)?(?![\w/])")
UNIT_AFTER = re.compile(r"\s*(" + "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True)) + r")(?![\w/])")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- 1. digest
def _u(unit: str) -> str:
    return "" if unit in ("ratio", "pH") else f" {unit}"


def digest(f: dict) -> str:
    p = f["patient"]
    lines = [f"Patient : {p['age']} ans, {'homme' if p['sex'] == 'M' else 'femme'}"
             + (f", tabagisme {fnum(p['pack_years'])} paquets-années" if p.get("pack_years") else "")
             + f". {f['reason']}."]
    for e in f["events"]:
        when = (f"du {fdate(e['date'])} au {fdate(e['end_date'])}" if e.get("end_date") and e["end_date"] != e["date"]
                else f"le {fdate(e['date'])}")
        lines.append(f"{EVENTS.get(e['type'], 'Événement')} {when}.")
    trends = {t["param"]: t for t in f["trends"]}
    alerted = {v.get("measurement_id") for a in f["alerts"] for v in a["values"]}
    for v in f["latest_values"]:
        t = trends.get(v["param"])
        salient = v["out_of_range"] or (t and t["qualification"] != "stable") or v["measurement_id"] in alerted
        if v["days_old"] > 183 or not salient:
            continue
        ctx = "".join(f" {CONTEXTS.get(c, c)}" for c in v["context"])
        s = f"{v['name']}{ctx} : {fnum(v['value'])}{_u(v['unit'])} le {fdate(v['date'])}"
        if v["out_of_range"]:
            s += " (hors de la zone de référence)"
        if v["previous"]:
            s += f", précédente {fnum(v['previous']['value'])}{_u(v['unit'])} le {fdate(v['previous']['date'])}"
        if t:
            s += f" ; tendance sur 12 mois : {TRENDS[t['qualification']].lower()}"
            if t["qualification"] != "stable" and t["slope_per_year"] is not None:
                s += f" ({fnum(float(format(t['slope_per_year'], '.3g')))}{_u(v['unit'])} par an)"
        lines.append(s + ".")
    for a in f["alerts"]:
        lines.append(f"Alerte{' acquittée' if a['state'] == 'acknowledged' else ''} : {a['label']} : {a['message']}.")
    r = f.get("radiographs")
    if r and r["comparisons"]:
        a, b = r["items"]
        for c in r["comparisons"]:
            name = PATHOLOGIES.get(c["pathology"], c["pathology"])
            lines.append(f"Radiographies du {fdate(a['date'])} et du {fdate(b['date'])} : score indicatif {name} "
                         f"{fnum(c['before'])} puis {fnum(c['after'])}, "
                         + ("variation dans la marge d'incertitude." if c["within_margin"]
                            else "variation au-delà de la marge d'incertitude."))
    rx = [t["molecule"] for t in f["treatments"]["current"]]
    if rx:
        lines.append(f"Traitements en cours : {', '.join(rx)}.")
    ch = f["treatments"].get("last_change")
    if ch:
        parts = ([f"ajout de {', '.join(ch['added'])}"] if ch["added"] else []) + (
            [f"arrêt de {', '.join(ch['stopped'])}"] if ch["stopped"] else [])
        lines.append(f"Dernier changement du traitement de fond le {fdate(ch['date'])} : {' ; '.join(parts)}.")
    return "\n".join(lines)


# ---------------------------------------------------------------- 2. vérificateur
def _num(s: str) -> float:
    return float(s.replace("−", "-").replace(",", "."))


def _decimals(s: str) -> int:
    m = re.search(r"[.,](\d+)$", s)
    return len(m.group(1)) if m else 0


def _dates(text: str) -> tuple[set[dt.date], set[tuple[int, int]], str]:
    """Dates numériques et en lettres ; renvoie aussi le texte où elles sont masquées."""
    full: set[dt.date] = set()
    months: set[tuple[int, int]] = set()

    def add(y: int, m: int, d: int) -> None:
        try:
            full.add(dt.date(y, m, d))
        except ValueError:
            full.add(dt.date.min)  # date impossible : ne correspondra à aucun fait

    def num(m: re.Match) -> str:
        add(int(m[3]), int(m[2]), int(m[1]))
        return " # "

    def words(m: re.Match) -> str:
        month = MONTHS.index(m[2]) + 1
        if m[1]:
            add(int(m[3]), month, int(m[1]))
        else:
            months.add((int(m[3]), month))
        return " # "

    return full, months, DATE_WORDS.sub(words, DATE_NUM.sub(num, text))


def _numbers(text: str) -> list[tuple[str, float, str | None]]:
    """(nombre écrit, valeur, unité qui le suit ou None)."""
    out = []
    for m in NUMBER.finditer(text):
        u = UNIT_AFTER.match(text, m.end())
        out.append((m.group(0), _num(m.group(0)), u.group(1) if u else None))
    return out


def _same(written: str, x: float, v: float) -> bool:
    """x (écrit avec n décimales) est un arrondi de v : |v − x| ≤ ½·10⁻ⁿ (0,125 -> « 0,13 » ou « 0,12 »).
    Un entier inférieur à 10 doit être exact (« 2 L » n'est pas un arrondi acceptable de 1,54 L)."""
    places = _decimals(written)
    if places == 0 and abs(v) < 10:
        return abs(abs(v) - abs(x)) < 1e-9
    return abs(abs(v) - abs(x)) <= 0.5 * 10 ** -places + 1e-9


def _names(source: str) -> set[str]:
    """Noms des paramètres décrits dans le digest (début de ligne, contexte de mesure retiré)."""
    out = set()
    for line in source.splitlines():
        if (m := re.match(rf"([^:]+?){CTX} : \d", line)) and not line.startswith("patient"):
            out.add(m[1].strip())
    return out


def _param_names(source: str) -> dict[str, str]:
    """Nom de paramètre (début de ligne du digest, avant « : ») -> qualification de sa tendance."""
    out = {}
    for line in source.splitlines():
        m = re.match(r"([^:]+?) : .*tendance sur 12 mois : (\w+)", line)
        if m:
            name = re.sub(r"\s+(post-bd|pre-bd|repos|air ambiant|effort|sous o2)\b", "", m[1]).strip()
            out[name] = {"degradation": "worsening", "amelioration": "improving", "stable": "stable"}[m[2]]
    return out


def verify(text: str, source: str) -> dict:
    """Contrôle un texte produit par le LLM contre le digest. `ok` faux dès qu'un élément n'est pas justifié."""
    issues: list[str] = []
    t, src = fold(text), fold(source)
    src_dates, _, src_rest = _dates(src)
    src_nums = _numbers(src_rest)
    src_years = {d.year for d in src_dates}

    dates, months, rest = _dates(t)
    issues += [f"date absente des faits : {d:%d/%m/%Y}" if d != dt.date.min else "date impossible"
               for d in dates if d not in src_dates]
    issues += [f"mois absent des faits : {m:02d}/{y}" for y, m in months
               if not any(d.year == y and d.month == m for d in src_dates)]
    numbers = _numbers(rest)
    for written, x, unit in numbers:
        if x == int(x) and int(x) in src_years and unit is None:
            continue
        candidates = [v for _, v, _ in src_nums] if unit is None else [v for _, v, u in src_nums if u == unit]
        if not any(_same(written, x, v) for v in candidates):
            issues.append(f"nombre absent des faits : {written}{' ' + unit if unit else ''}")

    for pat in FORBIDDEN:
        if m := re.search(rf"\b{pat}\b", t):
            issues.append(f"formulation interdite : {m.group(0)}")
    for disease in DISEASES:
        if re.search(rf"\b{disease}", t) and not re.search(rf"\b{disease}", src):
            issues.append(f"pathologie absente des faits : {disease}")

    params = _param_names(src)
    for sentence in re.split(r"(?<=[.;])\s+", t):
        words = {QUALIF[w.rstrip("s")] for w in re.findall(r"\w+", sentence) if w.rstrip("s") in QUALIF}
        if not words:
            continue
        rest_s = sentence
        for name in sorted(params, key=len, reverse=True):  # « rapport vems/cvf » avant « vems »
            if name in rest_s:
                rest_s = rest_s.replace(name, " ")
                if params[name] not in words:
                    issues.append(f"tendance contraire aux faits : {name}")
    out_of_range = {n for n in _names(src) if re.search(rf"^{re.escape(n)}{CTX} : [^\n]*hors de la zone", src, re.M)}
    for sentence in re.split(r"(?<=[.;])\s+", t):
        if "zone de reference" in sentence or "normale" in sentence:
            for name in sorted(_names(src), key=len, reverse=True):
                if name in sentence:
                    sentence = sentence.replace(name, " ")
                    if name not in out_of_range:
                        issues.append(f"position par rapport à la zone de référence non établie : {name}")
    if m := re.search(rf"\b{ACRONYMS}\s*\((?!%)", t):  # « VEMS (% prédit) » est un nom de paramètre
        issues.append(f"sigle développé (source d'erreur) : {m.group(0)}")
    if text.strip() and not text.strip().endswith((".", "!", ")")):
        issues.append("texte tronqué")
    within = "dans la marge d'incertitude" in src
    for sentence in re.split(r"(?<=[.;])\s+", t):
        if within and re.search(r"radiograph|score", sentence) and (m := MOVE.search(sentence)):
            issues.append(f"évolution radiographique non établie : {m.group(0)}")
    return {"ok": not issues, "issues": issues, "checked": len(numbers) + len(dates) + len(months)}


# ---------------------------------------------------------------- 3. rédaction
SYSTEM = (
    "Tu rédiges la synthèse d'une fiche de pré-consultation pour un pneumologue, en français. "
    "Utilise UNIQUEMENT les faits fournis, sans rien ajouter. Recopie les nombres, unités et dates exactement. "
    "Reprends les tendances telles qu'elles sont écrites (dégradation, amélioration, stable). "
    "Ne développe pas les sigles. Aucune interprétation, aucun diagnostic, aucune recommandation. "
    "Écris 3 à 5 phrases courtes, sans titre ni liste."
)


def draft(facts: dict) -> tuple[str | None, dict]:
    """Synthèse vérifiée, ou None après MAX_ATTEMPTS échecs. Le second essai reçoit les erreurs du premier."""
    source = digest(facts)
    attempts: list[dict] = []
    start = time.perf_counter()
    prompt = f"Faits :\n{source}"
    for _ in range(MAX_ATTEMPTS):
        t0 = time.perf_counter()
        text = re.sub(r"^voici[^\n]*:\s*", "", llm.generate_text(prompt, SYSTEM) or "", flags=re.I).strip()
        check = verify(text, source) if text else {"ok": False, "issues": ["LLM indisponible ou réponse vide"], "checked": 0}
        attempts.append({**check, "text": text, "seconds": round(time.perf_counter() - t0, 1)})
        if check["ok"]:
            break
        prompt = (f"Faits :\n{source}\n\nTa réponse précédente a été refusée : {'; '.join(check['issues'][:5])}. "
                  "Réécris la synthèse sans ces erreurs.")
    info = {"attempts": attempts, "seconds": round(time.perf_counter() - start, 1), "model": llm.model_name(),
            "source": source}
    return (attempts[-1]["text"] if attempts[-1]["ok"] else None), info
