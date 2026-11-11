"""Gabarits HTML des documents synthétiques.

4 gabarits de laboratoire (T1-T3 développement, T4 réservé au test : décision D9) qui diffèrent par la mise
en page, les libellés, les unités et le séparateur décimal. Chaque fonction renvoie (html, printed) où
`printed` liste, pour chaque valeur, le texte exactement imprimé et la valeur canonique correspondante :
c'est la vérité terrain d'extraction.
"""
from __future__ import annotations

import html as _html
from datetime import date
from pathlib import Path

import yaml

REF = yaml.safe_load((Path(__file__).resolve().parents[2] / "referential" / "referentiel_clinique.yaml")
                     .read_text(encoding="utf-8"))
REFS = {p["code"]: p.get("reference") for p in REF["parameters"]}
FOOTER = "Document fictif généré pour le projet MediMind (données synthétiques, aucune donnée réelle)."

# unité imprimée -> (facteur vers l'unité canonique, décimales affichées)
LAB_TEMPLATES = {
    "T1": {"lab": "Laboratoire Atlas d'Analyses Médicales", "addr": "Bd Anfa, Casablanca", "sep": ",",
           "layout": "table", "thousands": True,
           "labels": {"WBC": "Leucocytes", "NEUT": "Poly. neutrophiles", "LYMPH": "Lymphocytes",
                      "EOS": "Poly. éosinophiles", "HB": "Hémoglobine", "PLT": "Plaquettes",
                      "CRP": "Protéine C réactive", "PCT": "Procalcitonine", "CREAT": "Créatinine"},
           "units": {"WBC": ("/mm³", 0.001, -2), "NEUT": ("/mm³", 0.001, -1), "LYMPH": ("/mm³", 0.001, -1),
                     "EOS": ("/mm³", 0.001, -1), "HB": ("g/dL", 1, 1), "PLT": ("/mm³", 0.001, -3),
                     "CRP": ("mg/L", 1, 1), "PCT": ("ng/mL", 1, 2), "CREAT": ("mg/L", 1, 1)}},
    "T2": {"lab": "Laboratoire Al Amal de Biologie Médicale", "addr": "Av. Mohammed V, Rabat", "sep": ",",
           "layout": "anteriorite", "thousands": False,
           "labels": {"WBC": "GB", "NEUT": "PNN", "LYMPH": "Lymphocytes", "EOS": "PNE", "HB": "Hb",
                      "PLT": "Plaquettes", "CRP": "CRP", "PCT": "PCT", "CREAT": "Créatininémie"},
           "units": {"WBC": ("G/L", 1, 1), "NEUT": ("G/L", 1, 1), "LYMPH": ("G/L", 1, 1), "EOS": ("G/L", 1, 2),
                     "HB": ("g/L", 0.1, 0), "PLT": ("G/L", 1, 0), "CRP": ("mg/L", 1, 1), "PCT": ("µg/L", 1, 2),
                     "CREAT": ("µmol/L", 0.1131, 0)}},
    "T3": {"lab": "Biolab Hay Riad", "addr": "Hay Riad, Rabat", "sep": ",", "layout": "dotted", "thousands": False,
           "labels": {"WBC": "Globules blancs", "NEUT": "Neutrophiles", "LYMPH": "Lymphocytes",
                      "EOS": "Éosinophiles", "HB": "Hémoglobine", "PLT": "Plaquettes", "CRP": "C-réactive protéine",
                      "PCT": "Procalcitonine", "CREAT": "Créatinine"},
           "units": {"WBC": ("10³/µL", 1, 1), "NEUT": ("10³/µL", 1, 1), "LYMPH": ("10³/µL", 1, 1),
                     "EOS": ("10³/µL", 1, 2), "HB": ("g/dL", 1, 1), "PLT": ("10³/µL", 1, 0),
                     "CRP": ("mg/dL", 10, 2), "PCT": ("ng/mL", 1, 2), "CREAT": ("mg/dL", 10, 2)}},
    "T4": {"lab": "Centre d'Analyses Ibn Sina", "addr": "Rue Ibn Sina, Kénitra", "sep": ".", "layout": "unit_first",
           "thousands": False,
           "labels": {"WBC": "Leucocytes totaux", "NEUT": "Neutrophiles", "LYMPH": "Lymphocytes",
                      "EOS": "Eosinophiles", "HB": "Hemoglobine", "PLT": "Numération plaquettaire",
                      "CRP": "Protéine C-réactive", "PCT": "Procalcitonine", "CREAT": "Créatinine sérique"},
           "units": {"WBC": ("10^9/L", 1, 2), "NEUT": ("10^9/L", 1, 2), "LYMPH": ("10^9/L", 1, 2),
                     "EOS": ("10^9/L", 1, 2), "HB": ("g/L", 0.1, 0), "PLT": ("10^9/L", 1, 0),
                     "CRP": ("mg/L", 1, 1), "PCT": ("ng/mL", 1, 2), "CREAT": ("µmol/L", 0.1131, 0)}},
}
SECTIONS = [("Hématologie", ["WBC", "NEUT", "LYMPH", "EOS", "HB", "PLT"]),
            ("Biochimie", ["CRP", "PCT", "CREAT"])]
DOCTOR = "Dr Nadia Berrada"
CENTER = "Cabinet de Pneumologie Les Orangers, Casablanca"
EFR_CENTER = "Service d'Explorations Fonctionnelles Respiratoires, Clinique Al Boustane"


def esc(s) -> str:
    return _html.escape(str(s))


def fnum(x: float, dec: int, sep: str = ",", thousands: bool = False) -> str:
    v = round(x, dec)
    if dec <= 0:
        s = f"{int(round(v)):,}".replace(",", " " if thousands else "")
    else:
        s = f"{v:.{dec}f}"
        if thousands and abs(v) >= 1000:
            ip, fp = s.split(".")
            s = f"{int(ip):,}".replace(",", " ") + "." + fp
        s = s.replace(".", sep)
    return s


def fdate(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d/%m/%Y")


def printed_value(param: str, canon: float, unit: str, factor: float, dec: int, sep: str, thousands: bool,
                  label: str, context: list[str]) -> tuple[str, dict]:
    disp = round(canon / factor, dec)
    text = fnum(disp, dec, sep, thousands)
    return text, {"param": param, "label": label, "printed": text, "unit": unit,
                  "canonical_value": round(disp * factor, 4), "context": context}


def ref_text(param: str, factor: float, dec: int, sep: str) -> str:
    r = REFS.get(param)
    if not r:
        return ""
    lo, hi = r.get("low"), r.get("high")
    d = max(dec, 0) if factor >= 1 or dec > 0 else 0
    if lo in (None, 0) and hi is not None:
        return f"< {fnum(hi / factor, d, sep)}"
    if lo is not None and hi is not None:
        return f"{fnum(lo / factor, d, sep)} - {fnum(hi / factor, d, sep)}"
    return ""


BASE_CSS = """
@page { size: A4; margin: 16mm 16mm 18mm 16mm; }
body { font-family: %(font)s; font-size: 10.5pt; color: #111; }
.footer { position: fixed; bottom: 0; left: 0; right: 0; font-size: 7.5pt; color: #666; text-align: center; }
table { border-collapse: collapse; width: 100%%; }
"""


def page(body: str, font: str = "Arial, sans-serif", extra_css: str = "") -> str:
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><style>{BASE_CSS % {'font': font}}"
            f"{extra_css}</style></head><body>{body}<div class='footer'>{FOOTER}</div></body></html>")


def patient_block(p: dict) -> str:
    return (f"{esc(p['last_name'].upper())} {esc(p['first_name'])}, né(e) le {fdate(p['birth_date'])}, "
            f"{'Homme' if p['sex'] == 'M' else 'Femme'}")


# ------------------------------------------------------------------ bilan biologique
def lab_report(tpl_id: str, p: dict, doc: dict, prev: dict[str, float]) -> tuple[str, list[dict]]:
    t = LAB_TEMPLATES[tpl_id]
    vals = {v["param"]: v["value"] for v in doc["values"]}
    printed, rows = [], []
    for section, params in SECTIONS:
        sec_rows = []
        for prm in params:
            if prm not in vals:
                continue
            unit, factor, dec = t["units"][prm]
            label = t["labels"][prm]
            text, gt = printed_value(prm, vals[prm], unit, factor, dec, t["sep"], t["thousands"], label, [])
            printed.append(gt)
            ref = ref_text(prm, factor, dec, t["sep"])
            ante = fnum(round(prev[prm] / factor, dec), dec, t["sep"], t["thousands"]) if prm in prev else ""
            sec_rows.append((label, text, unit, ref, ante))
        rows.append((section, sec_rows))
    num = f"{doc['doc_id'][-3:]}{date.fromisoformat(doc['date']).strftime('%m%d')}"
    head_info = (f"Dossier n° {num}<br>Prélèvement du {fdate(doc['date'])} à 08:{10 + int(num[-2:]) % 40:02d}<br>"
                 f"Prescripteur : {DOCTOR}")
    if t["layout"] == "table":
        body = [f"<div class='hd'><div><b>{esc(t['lab'])}</b><br>{esc(t['addr'])}<br>Biologiste : Dr S. Kettani</div>"
                f"<div class='r'>{head_info}</div></div><p>Patient : {patient_block(p)}</p>"
                "<table><tr><th>Examen</th><th>Résultat</th><th>Unité</th><th>Valeurs usuelles</th></tr>"]
        for section, sr in rows:
            body.append(f"<tr><td colspan='4' class='sec'>{section.upper()}</td></tr>")
            body += [f"<tr><td>{esc(a)}</td><td><b>{b}</b></td><td>{esc(c)}</td><td>{esc(d)}</td></tr>"
                     for a, b, c, d, _ in sr]
        body.append("</table>")
        css = (".hd{display:flex;justify-content:space-between;border-bottom:2px solid #222;padding-bottom:6px}"
               ".r{text-align:right}th{text-align:left;border-bottom:1.5px solid #222;padding:4px}"
               "td{padding:4px;border-bottom:1px dotted #999}.sec{font-weight:bold;padding-top:10px}")
        return page("".join(body), "Georgia, serif", css), printed
    if t["layout"] == "anteriorite":
        body = [f"<div class='band'><b>{esc(t['lab'])}</b> &nbsp; {esc(t['addr'])}</div>"
                f"<table class='meta'><tr><td>{patient_block(p)}</td><td class='r'>{head_info}</td></tr></table>"
                "<table class='res'><tr><th>Paramètre</th><th>Valeur</th><th>Unité</th><th>Normes</th>"
                "<th>Antériorité</th></tr>"]
        for section, sr in rows:
            body.append(f"<tr><td colspan='5' class='sec'>{section}</td></tr>")
            body += [f"<tr><td>{esc(a)}</td><td class='v'>{b}</td><td>{esc(c)}</td><td>{esc(d)}</td>"
                     f"<td class='ante'>{e}</td></tr>" for a, b, c, d, e in sr]
        body.append("</table><p class='sm'>Antériorité : résultat précédent du patient dans notre laboratoire.</p>")
        css = (".band{background:#1f4e79;color:#fff;padding:8px 10px;font-size:12pt}.meta td{padding:8px 0}"
               ".r{text-align:right}.res th{background:#dde7f0;text-align:left;padding:5px}.res td{padding:5px;"
               "border:1px solid #c8d3dd}.v{font-weight:bold}.sec{background:#f2f5f8;font-weight:bold}"
               ".ante{color:#555;font-style:italic}.sm{font-size:8.5pt;color:#555}")
        return page("".join(body), "Arial, sans-serif", css), printed
    if t["layout"] == "dotted":
        body = [f"<h1>{esc(t['lab'])}</h1><p class='c'>{esc(t['addr'])}</p><hr>"
                f"<p>Nom : {patient_block(p)}<br>{head_info}</p><hr>"]
        for section, sr in rows:
            body.append(f"<h2>{section}</h2>")
            body += [f"<div class='l'><span>{esc(a)}</span><span class='dots'></span><span><b>{b}</b> {esc(c)}"
                     f"{' &nbsp;(' + esc(d) + ')' if d else ''}</span></div>" for a, b, c, d, _ in sr]
        css = ("h1{text-align:center;font-size:15pt;margin:0}.c{text-align:center;margin:2px}"
               "h2{font-size:11pt;text-decoration:underline;margin:14px 0 6px}"
               ".l{display:flex;align-items:baseline;margin:4px 0}.dots{flex:1;border-bottom:1.5px dotted #444;"
               "margin:0 6px}")
        return page("".join(body), "'Courier New', monospace", css), printed
    # unit_first (T4, réservé au test)
    body = [f"<table class='top'><tr><td><b style='font-size:13pt'>{esc(t['lab'])}</b><br>{esc(t['addr'])}</td>"
            f"<td class='r'>COMPTE RENDU D'ANALYSES<br>{head_info}</td></tr></table>"
            f"<p><i>Patient(e)</i> : {patient_block(p)}</p>"
            "<table class='res'><tr><th>Analyse</th><th>Unité</th><th>Résultat</th><th>Référence</th></tr>"]
    for _, sr in rows:
        body += [f"<tr><td>{esc(a)}</td><td>{esc(c)}</td><td class='v'>{b}</td><td>{esc(d)}</td></tr>"
                 for a, b, c, d, _ in sr]
    body.append("</table>")
    css = (".top td{vertical-align:top}.r{text-align:right;font-size:9.5pt}.res{margin-top:10px}"
           ".res th{border-top:2px solid #000;border-bottom:1px solid #000;text-align:left;padding:5px}"
           ".res td{padding:5px}.res tr:nth-child(even) td{background:#f1f1f1}.v{text-align:right;font-weight:bold}")
    return page("".join(body), "Verdana, sans-serif", css), printed


# ------------------------------------------------------------------ EFR
def efr_report(p: dict, doc: dict) -> tuple[str, list[dict]]:
    by = {}
    for v in doc["values"]:
        by[(v["param"], "pre" if "pre_bd" in v["context"] else "post")] = v
    bd = doc["text_hints"]["bd"]
    pf, pv = doc["text_hints"]["pred_fev1"], doc["text_hints"]["pred_fvc"]
    printed = []

    def cell(param, phase, unit, factor, dec, label):
        v = by.get((param, phase))
        if v is None:
            return ""
        text, gt = printed_value(param, v["value"], unit, factor, dec, ",", False, label, v["context"])
        printed.append(gt)
        return text

    rows = []
    for param, label, unit, factor, dec, pred in (("FEV1", "VEMS", "L", 1, 2, pf), ("FVC", "CVF", "L", 1, 2, pv),
                                                  ("FEV1_FVC", "VEMS/CVF", "%", 0.01, 0, None)):
        pre = cell(param, "pre", unit, factor, dec, label) if bd else None
        post = cell(param, "post", unit, factor, dec, label)
        pct_param = {"FEV1": "FEV1_PRED", "FVC": "FVC_PRED"}.get(param)
        pct = cell(pct_param, "post", "%", 1, 0, f"{label} % théorique") if pct_param else ""
        theo = fnum(pred, 2) if pred else ""
        rows.append((label, unit, theo, pre, post, pct))
    dlco = cell("DLCO_PRED", "post", "%", 1, 0, "DLCO % théorique") if ("DLCO_PRED", "post") in by else None
    head = (f"<div class='hd'><b>{EFR_CENTER}</b><br>Exploration fonctionnelle respiratoire du {fdate(doc['date'])}"
            f"</div><p>Patient : {patient_block(p)}<br>Taille : {p['height_cm']} cm. Prescripteur : {DOCTOR}</p>")
    if bd:
        th = "<tr><th>Paramètre</th><th>Unité</th><th>Théorique</th><th>Pré-BD</th><th>Post-BD</th><th>% Théo (post)</th></tr>"
        tr = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td><td><b>{e}</b></td><td>{f}</td></tr>"
                     for a, b, c, d, e, f in rows)
        note = "<p>Test de réversibilité après 400 µg de salbutamol.</p>"
    else:
        th = "<tr><th>Paramètre</th><th>Unité</th><th>Théorique</th><th>Mesuré</th><th>% Théo</th></tr>"
        tr = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td><b>{e}</b></td><td>{f}</td></tr>"
                     for a, b, c, d, e, f in rows)
        note = ""
    dl = f"<p>Transfert du CO : DLCO à <b>{dlco} %</b> de la valeur théorique.</p>" if dlco else ""
    css = (".hd{border:1.5px solid #333;padding:8px;text-align:center}th{background:#e8e8e8;padding:5px;"
           "border:1px solid #999}td{padding:5px;border:1px solid #bbb;text-align:center}td:first-child{text-align:left}")
    return page(head + f"<table>{th}{tr}</table>" + note + dl + "<p>Interprétation laissée au pneumologue prescripteur.</p>",
                "Arial, sans-serif", css), printed


# ------------------------------------------------------------------ compte rendu
def visit_report(p: dict, doc: dict, events: list[dict]) -> tuple[str, list[dict]]:
    h = doc["text_hints"]
    kind = h["kind"]
    printed, values = [], {v["param"]: v for v in doc["values"]}
    who = f"{'M.' if p['sex'] == 'M' else 'Mme'} {p['last_name']} {p['first_name']}"
    parts = []
    if "SPO2" in values:
        txt, gt = printed_value("SPO2", values["SPO2"]["value"], "%", 1, 0, ",", False, "SpO2", ["rest", "room_air"])
        printed.append(gt)
        spo2 = f"SpO2 à {txt} % au repos en air ambiant"
    if kind == "suivi":
        parts.append(f"Consultation de suivi de BPCO. {who} rapporte une dyspnée stable. {spo2}. "
                     "Auscultation : murmure vésiculaire diminué aux bases. Bonne observance des inhalateurs.")
    elif kind == "exacerbation":
        sev = " avec signes de gravité, hospitalisation demandée" if h.get("severe") else ""
        parts.append(f"Consultation non programmée pour exacerbation de BPCO : majoration de la dyspnée, "
                     f"expectoration purulente depuis 3 jours{sev}. {spo2}. Antibiothérapie et corticothérapie orale "
                     "prescrites. Radiographie thoracique demandée.")
    elif kind == "hospitalisation":
        gds = []
        for prm, lab, unit, dec in (("PH", "pH", "", 2), ("PAO2", "PaO2", "mmHg", 0), ("PACO2", "PaCO2", "mmHg", 0),
                                    ("HCO3", "HCO3-", "mmol/L", 0)):
            txt, gt = printed_value(prm, values[prm]["value"], unit or "pH", 1, dec, ",", False, lab, ["room_air"])
            printed.append(gt)
            gds.append(f"{lab} {txt}{(' ' + unit) if unit else ''}")
        parts.append(f"Compte rendu d'hospitalisation du {fdate(h['start'])} au {fdate(h['end'])}. {who}, hospitalisé(e) "
                     f"pour exacerbation de BPCO. Gaz du sang artériel à l'admission en air ambiant : {' ; '.join(gds)}. "
                     "Évolution favorable sous aérosols, antibiothérapie et corticothérapie. Retour à domicile.")
    elif kind == "bilan_initial":
        parts.append(f"Consultation pour bilan respiratoire. Pas de plainte aiguë. {spo2}. Examen clinique sans particularité.")
    elif kind == "pneumonie":
        parts.append(f"Fièvre à 39 °C, toux et douleur thoracique depuis 4 jours. Crépitants en base droite. {spo2}. "
                     "Diagnostic retenu : pneumonie communautaire. Antibiothérapie par amoxicilline-acide clavulanique.")
    elif kind == "controle_pneumonie":
        if h.get("non_normalizing"):
            parts.append(f"Contrôle à J14 : persistance d'une fébricule et CRP non normalisée. {spo2}. "
                         "Relais antibiotique par lévofloxacine, contrôle biologique dans 3 semaines.")
        else:
            parts.append(f"Consultation de contrôle après pneumonie. Apyrexie, amélioration clinique. {spo2}.")
    elif kind == "suivi_fibrose":
        parts.append(f"Suivi de pneumopathie interstitielle fibrosante. Dyspnée d'effort, toux sèche. {spo2}. "
                     "Crépitants velcro aux deux bases. EFR et scanner de contrôle selon le calendrier de suivi.")
    title = "Compte rendu d'hospitalisation" if kind == "hospitalisation" else "Compte rendu de consultation"
    body = (f"<div class='hd'><b>{DOCTOR}</b><br>Pneumologue<br>{CENTER}</div><h1>{title}</h1>"
            f"<p class='d'>Le {fdate(doc['date'])}</p><p>Patient : {patient_block(p)}</p>"
            + "".join(f"<p>{esc(x)}</p>" for x in parts) + f"<p class='sig'>{DOCTOR}</p>")
    css = (".hd{font-size:9.5pt;color:#333;border-bottom:1px solid #999;padding-bottom:6px}h1{font-size:14pt;"
           "text-align:center;margin:18px 0}.d{text-align:right}p{line-height:1.5}.sig{text-align:right;margin-top:30px}")
    return page(body, "'Times New Roman', serif", css), printed


# ------------------------------------------------------------------ ordonnance
def prescription(p: dict, doc: dict) -> tuple[str, list[dict]]:
    items = []
    for i, t in enumerate(doc["treatments"], 1):
        dur = f"Pendant {t['duration_days']} jours." if t["duration_days"] else "Traitement au long cours."
        items.append(f"<li><b>{esc(t['molecule'].capitalize())}</b> {esc(t['dosage'])}. {dur}</li>")
    body = (f"<div class='hd'><b>{DOCTOR}</b><br>Pneumologue, ancienne interne des hôpitaux<br>{CENTER}<br>"
            f"Tél. : 05 22 00 00 00 (fictif)</div><p class='d'>Casablanca, le {fdate(doc['date'])}</p>"
            f"<p>{patient_block(p)}</p><h1>Ordonnance</h1><ol>{''.join(items)}</ol>"
            f"<p class='sig'>{DOCTOR}</p>")
    css = (".hd{font-size:10pt}.d{text-align:right}h1{text-align:center;font-size:16pt;letter-spacing:1px}"
           "li{margin:10px 0;line-height:1.4}.sig{text-align:right;margin-top:40px;font-style:italic}")
    return page(body, "Georgia, serif", css), []
