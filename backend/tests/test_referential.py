import copy

import pytest
import yaml
from pydantic import ValidationError

from app.core.config import get_settings
from app.services.referential import Referential, get_referential


def raw() -> dict:
    return yaml.safe_load(get_settings().referential_path.read_text(encoding="utf-8"))


def test_referential_file_is_valid():
    ref = get_referential()
    assert ref.version == "0.1.0"
    assert len(ref.parameters) == 20
    assert len(ref.alert_rules) == 8
    assert all(len(r.source) > 5 for r in ref.alert_rules)


def test_rule_without_source_is_rejected():
    data = copy.deepcopy(raw())
    del data["alert_rules"][0]["source"]
    with pytest.raises(ValidationError):
        Referential.model_validate(data)


def test_rule_with_unknown_parameter_is_rejected():
    data = copy.deepcopy(raw())
    data["alert_rules"][0]["param"] = "INCONNU"
    with pytest.raises(ValidationError, match="paramètre inconnu"):
        Referential.model_validate(data)


def test_threshold_rule_requires_value():
    data = copy.deepcopy(raw())
    rule = next(r for r in data["alert_rules"] if r["type"] == "threshold")
    del rule["value"]
    with pytest.raises(ValidationError, match="champs manquants"):
        Referential.model_validate(data)


def test_parameters_synced_to_database(db):
    from app.db.models import Parameter
    assert db.get(Parameter, "FEV1").unit == "L"
    assert db.get(Parameter, "CRP").ref_high == 5
