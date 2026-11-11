"""Cas de référence des tendances et des alertes (exigence : 100 % de concordance, docs/PLAN.md §9)."""
import datetime as dt

import pytest

from app.services.alerts import TreatmentCourse, evaluate, evaluate_rule
from app.services.referential import get_referential
from app.services.trends import Point, qualify, theil_sen

REF = get_referential()
D = dt.date.fromisoformat


def pts(*pairs, ctx=()):
    return [Point(D(d), v, tuple(ctx)) for d, v in pairs]


def rule(rule_id):
    return next(r for r in REF.alert_rules if r.id == rule_id)


def fired(rule_id, points, courses=()):
    return evaluate_rule(rule(rule_id), REF, points, list(courses))


# ---------------------------------------------------------------- Theil-Sen et qualification
def test_theil_sen_is_robust_to_an_outlier():
    series = pts(("2025-01-01", 1.60), ("2025-04-01", 1.575), ("2025-07-01", 1.20), ("2025-10-01", 1.525),
                 ("2026-01-01", 1.50))
    assert theil_sen(series) == pytest.approx(-0.10, abs=0.01)


@pytest.mark.parametrize("values,expected", [
    ([1.62, 1.60, 1.51, 1.54, 1.50], "worsening"),   # -120 mL/an > mcid 100 mL
    ([1.62, 1.63, 1.60, 1.61, 1.62], "stable"),
    ([1.40, 1.48, 1.55, 1.60, 1.66], "improving"),
])
def test_fev1_qualification(values, expected):
    dates = ["2025-11-20", "2026-01-15", "2026-05-15", "2026-09-17", "2026-11-05"]
    assert qualify(REF.parameter("FEV1"), pts(*zip(dates, values, strict=False)), 3)["qualification"] == expected


def test_lower_is_better_for_crp():
    q = qualify(REF.parameter("CRP"), pts(("2026-01-01", 120), ("2026-01-04", 50), ("2026-01-15", 3)), 3)
    assert q["qualification"] == "improving"


def test_range_parameter_returning_to_normal_is_improving():
    q = qualify(REF.parameter("WBC"), pts(("2026-01-01", 16), ("2026-01-05", 12), ("2026-01-20", 7)), 3)
    assert q["qualification"] == "improving"


def test_too_few_points_is_insufficient():
    q = qualify(REF.parameter("FEV1"), pts(("2026-01-01", 1.6), ("2026-06-01", 1.4)), 3)
    assert q["qualification"] == "insufficient"


# ---------------------------------------------------------------- règles d'alerte
def test_obstruction_requires_post_bd_context():
    assert fired("OBS_FEV1_FVC", pts(("2026-01-01", 0.55), ctx=["post_bd"]))
    assert not fired("OBS_FEV1_FVC", pts(("2026-01-01", 0.55)))            # contexte inconnu : pas d'alerte
    assert not fired("OBS_FEV1_FVC", pts(("2026-01-01", 0.72), ctx=["post_bd"]))


def test_spo2_alert_only_at_rest_on_room_air():
    assert fired("SPO2_LOW", pts(("2026-01-01", 91), ctx=["rest", "room_air"]))
    assert not fired("SPO2_LOW", pts(("2026-01-01", 91), ctx=["exercise", "room_air"]))
    assert not fired("SPO2_LOW", pts(("2026-01-01", 92), ctx=["rest", "room_air"]))


def test_crp_rise_needs_value_above_10_and_increase():
    series = pts(("2026-01-01", 4), ("2026-02-10", 106), ("2026-02-25", 6), ("2026-03-10", 9), ("2026-04-01", 12))
    got = [a.date for a in fired("CRP_RISE", series)]
    assert got == [D("2026-02-10"), D("2026-04-01")]


def test_fev1_decline_over_12_months():
    decline = pts(("2025-11-20", 1.62), ("2026-01-15", 1.60), ("2026-05-15", 1.51), ("2026-09-17", 1.54),
                  ("2026-11-05", 1.50))
    alerts = fired("FEV1_DECLINE", decline)
    assert alerts and alerts[-1].current and "pente" in alerts[-1].message
    stable = pts(("2025-11-20", 1.62), ("2026-05-15", 1.60), ("2026-11-05", 1.58))
    assert not fired("FEV1_DECLINE", stable)


def test_fev1_decline_needs_three_points_over_half_window():
    assert not fired("FEV1_DECLINE", pts(("2026-01-01", 1.8), ("2026-02-01", 1.5), ("2026-03-01", 1.3)))


@pytest.mark.parametrize("rule_id,param,first,last,expected", [
    ("PPF_FVC", "FVC_PRED", 74, 67, True),     # -7 points
    ("PPF_FVC", "FVC_PRED", 74, 70, False),    # -4 points
    ("PPF_FVC", "FVC_PRED", 74, 69, True),     # -5 points : seuil inclus
    ("PPF_DLCO", "DLCO_PRED", 50, 40, True),
    ("PPF_DLCO", "DLCO_PRED", 50, 43, False),
])
def test_progression_criteria(rule_id, param, first, last, expected):
    series = pts(("2025-11-01", first), ("2026-03-01", (first + last) / 2), ("2026-10-15", last))
    assert bool(fired(rule_id, series)) is expected


def test_progression_ignores_variation_spread_over_more_than_a_year():
    series = pts(("2024-01-01", 74), ("2025-06-01", 70), ("2026-10-15", 66))
    assert not fired("PPF_FVC", series)


def test_crp_not_normalized_after_antibiotic():
    abx = [TreatmentCourse("antibiotic", D("2026-02-01"), "amoxicilline-acide clavulanique")]
    persists = pts(("2026-02-01", 180), ("2026-02-04", 70), ("2026-02-15", 32))
    assert fired("CRP_NOT_NORMALIZED", persists, abx)[0].date == D("2026-02-15")
    resolved = pts(("2026-02-01", 180), ("2026-02-04", 70), ("2026-02-15", 3))
    assert not fired("CRP_NOT_NORMALIZED", resolved, abx)
    assert not fired("CRP_NOT_NORMALIZED", persists, [])                       # pas d'antibiotique validé
    steroid = [TreatmentCourse("systemic_steroid", D("2026-02-01"))]
    assert not fired("CRP_NOT_NORMALIZED", persists, steroid)


def test_eosinophils_threshold_inclusive():
    assert fired("EOS_HIGH", pts(("2026-01-01", 0.30)))
    assert not fired("EOS_HIGH", pts(("2026-01-01", 0.29)))


def test_only_latest_value_is_current():
    alerts = fired("OBS_FEV1_FVC", pts(("2026-01-01", 0.55), ("2026-06-01", 0.54), ctx=["post_bd"]))
    assert [a.current for a in alerts] == [False, True]


def test_evaluate_all_rules_on_demo_like_patient():
    series = {
        "FEV1_FVC": pts(("2025-11-20", 0.46), ("2026-11-05", 0.49), ctx=["post_bd"]),
        "EOS": pts(("2026-11-05", 0.34)),
        "CRP": pts(("2026-01-15", 2.5), ("2026-02-10", 106.2)),
    }
    ids = {a.rule_id for a in evaluate(REF, series, [])}
    assert ids == {"OBS_FEV1_FVC", "EOS_HIGH", "CRP_RISE"}


def test_fibrosis_progression_rules_only_apply_to_fibrosis_patients():
    series = {"FVC_PRED": pts(("2025-11-20", 91), ("2026-05-15", 84), ("2026-11-05", 78))}
    assert "PPF_FVC" not in {a.rule_id for a in evaluate(REF, series, [], ["bpco"])}
    assert "PPF_FVC" not in {a.rule_id for a in evaluate(REF, series, [], [])}
    assert "PPF_FVC" in {a.rule_id for a in evaluate(REF, series, [], ["fibrose"])}


def test_messages_use_points_for_percentage_changes_and_no_unit_for_ratio():
    fvc = fired("PPF_FVC", pts(("2025-11-20", 74), ("2026-05-15", 70), ("2026-11-05", 67)))
    assert fvc[-1].message.endswith("(-7 points)")
    ratio = fired("OBS_FEV1_FVC", pts(("2026-01-01", 0.55), ctx=["post_bd"]))
    assert ratio[0].message == "0,55 le 01/01/2026"
