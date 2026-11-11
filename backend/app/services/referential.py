"""Chargement et validation du référentiel clinique (referential/referentiel_clinique.yaml).

Le schéma Pydantic garantit au démarrage que chaque paramètre et chaque règle est complet ; une règle
sans source bibliographique ou pointant vers un paramètre inconnu empêche l'application de démarrer.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Parameter as ParameterRow


class Reference(BaseModel):
    low: float | None = None
    high: float | None = None
    note: str | None = None


class Mcid(BaseModel):
    abs: float
    source: str | None = None


class ParameterDef(BaseModel):
    code: str
    name: str
    category: Literal["efr", "vital", "bio", "gds"]
    synonyms: list[str] = Field(default_factory=list)
    unit: str
    alt_units: dict[str, float] = Field(default_factory=dict)
    plausible: tuple[float, float]
    reference: Reference | None = None
    mcid: Mcid
    better: Literal["higher", "lower", "range"]


class AlertRule(BaseModel):
    id: str
    label: str
    type: Literal["threshold", "delta_window", "rise", "after_treatment"]
    param: str
    severity: Literal["info", "warning"]
    source: str = Field(min_length=5)
    op: Literal["<", "<=", ">", ">="] | None = None
    value: float | None = None
    value_gt: float | None = None
    require_context: list[str] = Field(default_factory=list)
    window_days: int | None = None
    min_points: int | None = None
    method: Literal["theil_sen", "first_last"] | None = None
    delta_abs_lte: float | None = None
    vs_previous: Literal["increase"] | None = None
    treatment_class: str | None = None
    min_days_after_start: int | None = None
    note: str | None = None

    @model_validator(mode="after")
    def check_fields(self) -> AlertRule:
        required = {
            "threshold": ("op", "value"),
            "delta_window": ("window_days", "delta_abs_lte", "method"),
            "rise": ("value_gt", "vs_previous"),
            "after_treatment": ("value_gt", "treatment_class", "min_days_after_start"),
        }[self.type]
        missing = [f for f in required if getattr(self, f) is None]
        if missing:
            raise ValueError(f"règle {self.id} : champs manquants {missing}")
        return self


class Referential(BaseModel):
    version: str
    population: Literal["adult"]
    validated_by: str
    contexts: dict[str, str]
    parameters: list[ParameterDef]
    trend_qualification: dict
    alert_rules: list[AlertRule]
    treatment_classes: dict[str, list[str]]

    @model_validator(mode="after")
    def check_consistency(self) -> Referential:
        codes = {p.code for p in self.parameters}
        if len(codes) != len(self.parameters):
            raise ValueError("codes de paramètres en double")
        for r in self.alert_rules:
            if r.param not in codes:
                raise ValueError(f"règle {r.id} : paramètre inconnu {r.param}")
            unknown_ctx = set(r.require_context) - set(self.contexts)
            if unknown_ctx:
                raise ValueError(f"règle {r.id} : contexte inconnu {unknown_ctx}")
            if r.treatment_class and r.treatment_class not in self.treatment_classes:
                raise ValueError(f"règle {r.id} : classe de traitement inconnue {r.treatment_class}")
        return self

    def parameter(self, code: str) -> ParameterDef:
        return next(p for p in self.parameters if p.code == code)


def load_referential(path: Path) -> Referential:
    return Referential.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache
def get_referential() -> Referential:
    return load_referential(get_settings().referential_path)


def sync_parameters(db: Session, ref: Referential) -> None:
    """Recopie les paramètres du YAML dans la table `parameters` (clé étrangère des mesures)."""
    for p in ref.parameters:
        row = db.get(ParameterRow, p.code) or ParameterRow(code=p.code)
        row.name, row.category, row.synonyms, row.unit, row.alt_units = (
            p.name, p.category, p.synonyms, p.unit, p.alt_units)
        row.plausible_min, row.plausible_max = p.plausible
        row.ref_low = p.reference.low if p.reference else None
        row.ref_high = p.reference.high if p.reference else None
        db.add(row)
    db.commit()
