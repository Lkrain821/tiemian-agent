import pytest

from app.core.settings import Settings
from app.decision.client import DecisionServiceError
from app.graph.v1.routing import route_assessment


def state(probability=0.95, confidence=0.9, count=0, target="point_0"):
    return {"answer_assessment": {
        "decision_source": "jev", "followup_probability": probability,
        "followup_confidence": confidence, "followup_target": target,
    }, "current_followup_count": count, "max_followups": 2}


@pytest.mark.parametrize("probability,route", [
    (0.95, "followup"), (0.71, "followup"), (0.70, "followup"),
    (0.69, "fallback"), (0.50, "fallback"), (0.31, "fallback"),
    (0.30, "score"), (0.10, "score"),
])
def test_probability_boundaries(probability, route):
    assert route_assessment(state(probability)) == route


def test_confidence_limit_and_target():
    assert route_assessment(state(confidence=0.59)) == "fallback"
    assert route_assessment(state(confidence=0.60)) == "followup"
    assert route_assessment(state(count=2, confidence=0.0)) == "score"
    assert route_assessment(state(target=None)) == "fallback"
    assert route_assessment(state(probability=0.1, target=None)) == "score"


def test_custom_thresholds_and_disabled_fallback(settings):
    settings.jev_followup_threshold = 0.9
    assert route_assessment(state(0.8), settings) == "fallback"
    settings.jev_fallback_enabled = False
    with pytest.raises(DecisionServiceError):
        route_assessment(state(0.8), settings)
    assert route_assessment(state(count=2), settings) == "score"


@pytest.mark.parametrize("values", [
    {"jev_score_threshold": 0.8, "jev_followup_threshold": 0.7},
    {"jev_score_threshold": 0.7, "jev_followup_threshold": 0.7},
    {"jev_min_confidence": float("nan")}, {"jev_timeout_seconds": 0},
    {"decision_provider": "unknown"}, {"jev_base_url": "http://unsafe.example"},
])
def test_invalid_settings(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, deepseek_api_key="test", **values)
