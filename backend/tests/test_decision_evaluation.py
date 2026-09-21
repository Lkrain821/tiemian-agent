import copy
import json

import pytest

from app.decision.evaluate import DEFAULT_CASES, load_cases, summarize
from app.decision.client import DeepSeekAssessmentClient
from tests.fakes import FakeInterviewLLM


def test_fixture_coverage_and_labels():
    data = load_cases(DEFAULT_CASES)
    assert len(data["cases"]) == 56
    assert "unreviewed" in data["label_status"]
    assert len({case["category"] for case in data["cases"]}) == 8
    assert all(case["label_origin"] == "assistant_authored_synthetic_unreviewed" for case in data["cases"])


def test_reject_unknown_label(tmp_path):
    data = copy.deepcopy(load_cases(DEFAULT_CASES))
    data["cases"][0]["expected"] = {"followup": True, "target": "unknown"}
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown"):
        load_cases(path)


def test_metrics_do_not_count_fallback_as_jev_accuracy():
    rows = [
        {"expected": {"followup": True, "target": "point_0"},
         "deepseek": {"followup_needed": True},
         "jev": {"followup_target": "point_0"}, "jev_route": "followup",
         "jev_latency_ms": 100, "deepseek_latency_ms": 200},
        {"expected": {"followup": False, "target": None},
         "deepseek": {"followup_needed": False},
         "jev": None, "jev_route": "fallback", "jev_latency_ms": 300},
    ]
    metrics = summarize(rows, "synthetic_unreviewed")
    assert metrics["jev_direct_label_agreement"] == 1
    assert metrics["jev_direct_coverage"] == 0.5
    assert metrics["fallback_rate"] == 0.5
    assert metrics["mean_jev_latency_ms"] == 200
    assert metrics["mean_call_cost"] is None


def test_empty_metrics_are_unknown():
    result = summarize([], "unreviewed")
    assert result["jev_direct_label_agreement"] is None
    assert result["mean_call_cost"] is None


async def test_all_fixtures_pass_real_deepseek_prompt_adapter():
    baseline = DeepSeekAssessmentClient(FakeInterviewLLM())
    for case in load_cases(DEFAULT_CASES)["cases"]:
        result = await baseline.assess_answer(**{
            key: case[key] for key in ("question", "turns", "followup_count")
        })
        assert result.answer_relevance in {"relevant", "partially_relevant", "off_topic"}
