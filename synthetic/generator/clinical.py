"""Simulation clinique : identité, visites, trajectoires, événements, traitements et plan des documents.

Sortie : un « record » (dict JSON-sérialisable) par patient. Les valeurs sont en unités canoniques du
référentiel (referential/referentiel_clinique.yaml) ; la mise en forme par gabarit se fait dans templates.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

# ---------------------------------------------------------------- identités fictives
FIRST_M = ["Karim", "Youssef", "Hassan", "Mohamed", "Rachid", "Abdelaziz", "Mustapha", "Driss", "Said", "Omar",
           "Brahim", "Hamid", "Jamal", "Larbi", "Mehdi", "Noureddine", "Abdellah", "Khalid"]
FIRST_F = ["Fatima", "Khadija", "Naima", "Aicha", "Malika", "Zineb", "Latifa", "Rachida", "Samira", "Hayat",
           "Saida", "Nadia", "Amina", "Halima", "Souad", "Loubna", "Meryem", "Hafsa"]
LAST = ["Alaoui", "Bennani", "Chraibi", "Idrissi", "Tazi", "El Fassi", "Berrada", "Lahlou", "Benjelloun", "Sqalli",
        "Kettani", "Ouazzani", "Naciri", "Bouzid", "Cherkaoui", "Hajji", "Ziani", "Filali", "Mansouri"]
CITIES = ["Casablanca", "Rabat", "Salé", "Kénitra", "Mohammedia", "El Jadida"]

PARCOURS = {"A": "copd", "B": "pneumonia", "C": "fibrosis"}

# Traitements (DCI, classe du référentiel, posologie)
TIOTROPIUM = ("tiotropium", "lama", "2,5 µg, 2 inhalations le matin")
SALM_FLUT = ("salmétérol/fluticasone", "laba+ics", "50/500 µg, 1 inhalation matin et soir")
SALBUTAMOL = ("salbutamol", "saba", "100 µg, 2 bouffées si besoin")
AMOX_CLAV = ("amoxicilline-acide clavulanique", "antibiotic", "1 g/125 mg, 3 fois par jour")
LEVOFLOX = ("lévofloxacine", "antibiotic", "500 mg, 1 fois par jour")
PREDNISOLONE = ("prednisolone", "systemic_steroid", "40 mg, 1 fois par jour le matin")
NINTEDANIB = ("nintédanib", "antifibrotic", "150 mg, 2 fois par jour")
PIRFENIDONE = ("pirfénidone", "antifibrotic", "801 mg, 3 fois par jour")


def predicted(sex: str, age: int, height_cm: int) -> tuple[float, float]:
    """Valeurs théoriques VEMS et CVF (L), équations ECSC (Quanjer 1993)."""
    h = height_cm / 100
    if sex == "M":
        return 4.30 * h - 0.029 * age - 2.49, 5.76 * h - 0.026 * age - 4.34
    return 3.95 * h - 0.025 * age - 2.60, 4.43 * h - 0.026 * age - 2.89


@dataclass
class Doc:
    doc_id: str
    type: str                      # bilan_bio | efr | compte_rendu | ordonnance | radiographie
    date: date
    values: list[dict] = field(default_factory=list)       # {param, value, context}
    treatments: list[dict] = field(default_factory=list)   # {molecule, class, dosage, duration_days}
    events: list[dict] = field(default_factory=list)       # {type, date, end?}
    text_hints: dict = field(default_factory=dict)         # éléments narratifs pour le compte rendu
    nih_image: str | None = None
    nih_labels: str | None = None


class PatientSim:
    def __init__(self, pid: str, parcours: str, nih: dict, rng: np.random.Generator, start: date):
        self.pid, self.parcours, self.rng, self.start = pid, parcours, rng, start
        self.sex = nih["sex"]
        self.age = int(np.clip(nih["age"] + rng.integers(-2, 3), 40 if parcours != "B" else 25, 85))
        self.height = int(rng.normal(172 if self.sex == "M" else 160, 6))
        names = FIRST_M if self.sex == "M" else FIRST_F
        self.first, self.last = str(rng.choice(names)), str(rng.choice(LAST))
        self.birth = date(start.year - self.age, int(rng.integers(1, 13)), int(rng.integers(1, 28)))
        self.pack_years = {"A": int(rng.integers(25, 60)), "B": int(rng.choice([0, 0, 10, 20])),
                           "C": int(rng.choice([0, 0, 15, 30]))}[parcours]
        self.nih = nih
        self.docs: list[Doc] = []
        self.events: list[dict] = []
        self.treatments: list[dict] = []
        self._n = 0

    # ------------------------------------------------------------ utilitaires
    def doc(self, type_: str, d: date, **kw) -> Doc:
        self._n += 1
        doc = Doc(f"{self.pid}-D{self._n:03d}", type_, d, **kw)
        self.docs.append(doc)
        return doc

    def prescribe(self, d: date, items: list[tuple], durations: list[int | None], reason: str) -> Doc:
        tr = [{"molecule": m, "class": c, "dosage": dose, "duration_days": dur}
              for (m, c, dose), dur in zip(items, durations)]
        doc = self.doc("ordonnance", d, treatments=tr, text_hints={"reason": reason})
        for t in tr:
            end = d + timedelta(days=t["duration_days"]) if t["duration_days"] else None
            self.treatments.append({**t, "start": d, "end": end, "source_doc": doc.doc_id})
        return doc

    def bio(self, d: date, crp: float, wbc: float, eos: float, *, pct: float | None = None, creat: bool = False,
            neut_frac: float | None = None) -> Doc:
        r = self.rng
        neut_frac = neut_frac if neut_frac is not None else r.uniform(0.55, 0.68)
        vals = [("WBC", wbc), ("NEUT", wbc * neut_frac), ("LYMPH", wbc * r.uniform(0.18, 0.28)), ("EOS", eos),
                ("HB", r.normal(14.2 if self.sex == "M" else 12.9, 0.6)), ("PLT", r.normal(250, 45)), ("CRP", crp)]
        if pct is not None:
            vals.append(("PCT", pct))
        if creat:
            vals.append(("CREAT", r.normal(9.5 if self.sex == "M" else 7.5, 1.0)))
        return self.doc("bilan_bio", d, values=[{"param": p, "value": float(v), "context": []} for p, v in vals])

    def visit_note(self, d: date, spo2: float, kind: str, **hints) -> Doc:
        return self.doc("compte_rendu", d,
                        values=[{"param": "SPO2", "value": float(spo2), "context": ["rest", "room_air"]}],
                        text_hints={"kind": kind, **hints})

    def efr(self, d: date, fev1_post: float, fvc_post: float, *, bd: bool = True, dlco_pct: float | None = None) -> Doc:
        pf, pv = predicted(self.sex, self.age, self.height)
        vals = []
        if bd:
            fev1_pre, fvc_pre = fev1_post / self.rng.uniform(1.04, 1.10), fvc_post / self.rng.uniform(1.02, 1.06)
            vals += [{"param": "FEV1", "value": fev1_pre, "context": ["pre_bd"]},
                     {"param": "FVC", "value": fvc_pre, "context": ["pre_bd"]},
                     {"param": "FEV1_FVC", "value": fev1_pre / fvc_pre, "context": ["pre_bd"]}]
        ctx = ["post_bd"] if bd else []
        vals += [{"param": "FEV1", "value": fev1_post, "context": ctx},
                 {"param": "FVC", "value": fvc_post, "context": ctx},
                 {"param": "FEV1_FVC", "value": fev1_post / fvc_post, "context": ctx},
                 {"param": "FEV1_PRED", "value": 100 * fev1_post / pf, "context": ctx},
                 {"param": "FVC_PRED", "value": 100 * fvc_post / pv, "context": ctx}]
        if dlco_pct is not None:
            vals.append({"param": "DLCO_PRED", "value": dlco_pct, "context": []})
        return self.doc("efr", d, values=vals, text_hints={"bd": bd, "pred_fev1": pf, "pred_fvc": pv})

    def event(self, type_: str, d: date, end: date | None = None, note: str = "") -> dict:
        e = {"type": type_, "date": d, "end": end, "note": note}
        self.events.append(e)
        return e

    def place_radios(self, radio_dates: list[date]) -> None:
        imgs = self.nih["images"]
        for d, im in zip(sorted(radio_dates), imgs):
            self.doc("radiographie", d, nih_image=im["image"], nih_labels=im["labels"])

    # ------------------------------------------------------------ parcours A : BPCO avec exacerbations
    def simulate_A(self, demo: bool = False) -> None:
        r, s = self.rng, self.start
        pf, pv = predicted(self.sex, self.age, self.height)
        fev1_0 = float(np.clip(r.uniform(0.40, 0.65) * pf, 0.8, 2.6))
        ratio = r.uniform(0.45, 0.64)
        decline_before, decline_after = r.uniform(0.12, 0.22), r.uniform(0.02, 0.06)  # L/an
        eos0 = r.uniform(0.12, 0.45)
        sched = [s + timedelta(days=int(d)) for d in (0, 90 + r.integers(-10, 10), 180 + r.integers(-10, 10),
                                                       270 + r.integers(-10, 10), 355 + r.integers(-5, 5))]
        n_exa = 2 if demo else int(r.integers(1, 4))
        exa_days = sorted(r.choice(np.arange(40, 330), size=n_exa, replace=False))
        if demo:
            sched = [date(2025, 11, 20), date(2026, 1, 15), date(2026, 5, 15), date(2026, 8, 21), date(2026, 11, 5)]
            exa_days = [(date(2026, 2, 10) - s).days, (date(2026, 8, 20) - s).days]
        exa_dates = [s + timedelta(days=int(d)) for d in exa_days]
        # Pas d'EFR ni de bilan « de base » pendant une exacerbation : visite reportée à J28.
        for _ in range(2):
            sched = sorted({max([v] + [e + timedelta(days=28) for e in exa_dates if 0 <= (v - e).days < 28])
                            for v in sched})
        change_date = exa_dates[0] + timedelta(days=int(r.integers(14, 25)))

        def fev1_at(d: date) -> float:
            t = (d - s).days / 365
            tc = (change_date - s).days / 365
            base = fev1_0 - decline_before * min(t, tc) - decline_after * max(0.0, t - tc)
            dip = sum(0.18 * np.exp(-(d - e).days / 30) for e in exa_dates if d >= e)
            return float(base - dip + r.normal(0, 0.03))

        self.prescribe(s, [TIOTROPIUM, SALBUTAMOL], [None, None], "Traitement de fond")
        radio_dates = [s]
        for i, e in enumerate(exa_dates):
            severe = demo and i == 0 or (not demo and r.random() < 0.4)
            crp, wbc = r.uniform(35, 120), r.uniform(11, 16.5)
            spo2 = r.uniform(87, 91.5) if severe else r.uniform(90, 93)
            self.event("exacerbation", e, note="Majoration de la dyspnée et expectoration purulente")
            self.bio(e, crp, wbc, eos0 * r.uniform(0.6, 0.9), pct=r.uniform(0.15, 0.9), creat=True, neut_frac=0.78)
            self.visit_note(e, spo2, "exacerbation", severe=severe)
            self.prescribe(e, [AMOX_CLAV, PREDNISOLONE], [7, 5], "Exacerbation de BPCO")
            if severe:
                h_end = e + timedelta(days=int(r.integers(4, 8)))
                self.event("hospitalisation", e + timedelta(days=1), end=h_end, note="Hospitalisation pour exacerbation")
                ph, paco2 = r.uniform(7.33, 7.40), r.uniform(44, 54)
                self.doc("compte_rendu", h_end, values=[
                    {"param": "PH", "value": ph, "context": ["room_air"]},
                    {"param": "PAO2", "value": r.uniform(55, 64), "context": ["room_air"]},
                    {"param": "PACO2", "value": paco2, "context": ["room_air"]},
                    {"param": "HCO3", "value": r.uniform(26, 31), "context": ["room_air"]}],
                    text_hints={"kind": "hospitalisation", "start": e + timedelta(days=1), "end": h_end})
            ctrl = e + timedelta(days=int(r.integers(12, 18)))
            self.bio(ctrl, r.uniform(4, 14), r.uniform(7, 10), eos0, creat=False)
            radio_dates.append(e + timedelta(days=1))
            if i == 0:
                self.event("treatment_change", change_date, note="Ajout salmétérol/fluticasone")
                self.prescribe(change_date, [TIOTROPIUM, SALM_FLUT, SALBUTAMOL], [None, None, None],
                               "Renforcement du traitement de fond après exacerbation")
        for k, v in enumerate(sched):
            f1 = fev1_at(v)
            fvc = f1 / float(np.clip(ratio + r.normal(0, 0.015), 0.40, 0.68))
            self.efr(v, f1, fvc, bd=True, dlco_pct=r.uniform(45, 70) if k == 0 else None)
            self.bio(v, r.uniform(1, 6), r.uniform(6, 9.5), float(np.clip(eos0 + r.normal(0, 0.04), 0.05, 0.6)),
                     creat=(k % 2 == 0))
            self.visit_note(v, float(np.clip(r.normal(94, 1.0), 91, 97)), "suivi")
            if k in (2, 4):
                radio_dates.append(v)
        self.place_radios(sorted(set(radio_dates)))

    # ------------------------------------------------------------ parcours B : pneumonie et résolution
    def simulate_B(self) -> None:
        r = self.rng
        imgs = self.nih["images"]
        first_pos = next(i for i, im in enumerate(imgs) if any(x in im["labels"] for x in ("Pneumonia", "Consolidation")))
        j0 = self.start + timedelta(days=60 * first_pos)
        prior = [j0 - timedelta(days=60 * (first_pos - i)) for i in range(first_pos)]
        for d in prior:
            self.visit_note(d, float(np.clip(r.normal(97, 1), 94, 99)), "bilan_initial")
        non_normalizing = r.random() < 0.25
        crp0, wbc0, pct0 = r.uniform(90, 260), r.uniform(12.5, 20), r.uniform(0.6, 6)
        self.event("pneumonie", j0, note="Pneumonie communautaire")
        self.bio(j0, crp0, wbc0, r.uniform(0.02, 0.15), pct=pct0, creat=True, neut_frac=0.82)
        self.visit_note(j0, r.uniform(90, 94), "pneumonie")
        self.prescribe(j0, [AMOX_CLAV], [8], "Pneumonie communautaire")
        half_life = r.uniform(1.6, 2.4)
        days = [3, 14, 35, 90, 180]
        switch = None
        for dd in days:
            d = j0 + timedelta(days=dd)
            if non_normalizing and dd == 14:
                crp = r.uniform(18, 45)
                switch = d
            elif switch is not None:
                crp = max(1.0, 30 * np.exp(-(d - switch).days / 4) + r.uniform(0.5, 4))
            else:
                crp = max(1.0, crp0 * 0.5 ** (dd / half_life) + r.uniform(0.5, 3))
            wbc = 4.5 + (wbc0 - 4.5) * np.exp(-dd / 5) + r.uniform(1, 3)
            self.bio(d, float(crp), float(wbc), r.uniform(0.05, 0.3), pct=r.uniform(0.02, 0.2) if dd <= 14 else None)
            if dd >= 14:
                spo2 = float(np.clip(r.normal(96, 1), 93, 99)) if (switch is None or dd > 30) else r.uniform(92, 95)
                self.visit_note(d, spo2, "controle_pneumonie", non_normalizing=(d == switch))
            if d == switch:
                self.event("treatment_change", d, note="Relais antibiotique pour CRP non normalisée")
                self.prescribe(d, [LEVOFLOX], [10], "CRP non normalisée à J14, relais antibiotique")
        radio_dates = prior + [j0, j0 + timedelta(days=35), j0 + timedelta(days=90), j0 + timedelta(days=180),
                               j0 + timedelta(days=240), j0 + timedelta(days=300)]
        self.place_radios(radio_dates[:len(imgs)])

    # ------------------------------------------------------------ parcours C : fibrose pulmonaire
    def simulate_C(self, progressive: bool) -> None:
        r, s = self.rng, self.start
        pf, pv = predicted(self.sex, self.age, self.height)
        fvc_pct0, dlco0 = r.uniform(58, 85), r.uniform(38, 65)
        fvc_decl = r.uniform(6, 10) if progressive else r.uniform(0.5, 2.5)    # % prédit / an
        dlco_decl = r.uniform(11, 16) if progressive else r.uniform(1, 5)
        ratio = r.uniform(0.80, 0.90)
        visits = [s + timedelta(days=int(d)) for d in (0, 110, 220, 330, 420)]
        self.prescribe(s, [SALBUTAMOL], [None], "Traitement symptomatique")
        anti = NINTEDANIB if r.random() < 0.5 else PIRFENIDONE
        for k, v in enumerate(visits):
            t = (v - s).days / 365
            fvc_pct = fvc_pct0 - fvc_decl * t + r.normal(0, 0.8)
            dlco = dlco0 - dlco_decl * t + r.normal(0, 1.0)
            fvc = fvc_pct * pv / 100
            self.efr(v, fvc * ratio, fvc, bd=False, dlco_pct=dlco)
            self.bio(v, r.uniform(1, 8), r.uniform(5.5, 9), r.uniform(0.05, 0.3), creat=True)
            self.visit_note(v, float(np.clip(96 - 2.5 * t * (2 if progressive else 0.6) + r.normal(0, 0.7), 86, 99)),
                            "suivi_fibrose")
            if k == 1:
                self.event("treatment_change", v, note=f"Introduction {anti[0]}")
                self.prescribe(v, [anti, SALBUTAMOL], [None, None], "Traitement antifibrosant")
        self.place_radios([visits[i] for i in (0, 2, 3, 4)][:len(self.nih["images"])])

    # ------------------------------------------------------------ export
    def record(self) -> dict:
        def ser(o):
            if isinstance(o, date):
                return o.isoformat()
            if isinstance(o, dict):
                return {k: ser(v) for k, v in o.items()}
            if isinstance(o, list):
                return [ser(x) for x in o]
            if isinstance(o, (np.floating,)):
                return float(o)
            return o
        docs = sorted(self.docs, key=lambda d: (d.date, d.doc_id))
        return ser({
            "patient": {"id": self.pid, "parcours": self.parcours, "first_name": self.first, "last_name": self.last,
                        "sex": self.sex, "birth_date": self.birth, "height_cm": self.height,
                        "pack_years": self.pack_years, "city": str(self.rng.choice(CITIES)),
                        "nih_patient_id": self.nih["patient_id"]},
            "events": sorted(self.events, key=lambda e: e["date"]),
            "treatments": sorted(self.treatments, key=lambda t: t["start"]),
            "documents": [{"doc_id": d.doc_id, "type": d.type, "date": d.date, "values": d.values,
                           "treatments": d.treatments, "text_hints": d.text_hints,
                           "nih_image": d.nih_image, "nih_labels": d.nih_labels} for d in docs],
        })
