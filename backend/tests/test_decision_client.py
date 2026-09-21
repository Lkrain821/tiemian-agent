"""Verify the real HTTP contract without calling a paid provider."""

import asyncio
import copy
import json

import httpx
import pytest

from app.decision.assessment import build_request, parse_response
from app.decision.client import DecisionServiceError, JevDecisionClient


QUESTION = {"stem": "如何恢复面试状态？", "rubric_points": {"key_points": ["checkpoint", "resume"]}}
TURNS = [{"role": "candidate", "content": "使用 checkpoint。"}]


def response_body(probability=0.8, target="point_1", confidence=0.9):
    return {"answers": {
        "relevance": {"type": "choice", "choice": "relevant", "confidence": confidence,
                      "probabilities": {"relevant": 0.9, "partially_relevant": 0.1, "off_topic": 0.0}},
        "target": {"type": "choice", "choice": target, "confidence": confidence,
                   "probabilities": {key: 1.0 if key == target else 0.0
                                     for key in ["point_0", "point_1", "none"]}},
        "followup": {"type": "noul", "noul": probability},
    }}


def test_request_contains_evidence_and_fixed_choices():
    body = build_request(QUESTION, TURNS, 1, "jev-latest")
    assert body["state"]["turns"] == TURNS
    assert body["state"]["followup_count"] == 1
    assert body["questions"]["target"]["criteria"]["point_1"] == "resume"
    assert set(body["questions"]) == {"target", "relevance", "followup"}


@pytest.mark.parametrize("target", ["point_0", "point_1", "none"])
def test_parser(target):
    decision = parse_response(response_body(target=target), QUESTION)
    assert decision.followup_target == (None if target == "none" else target)
    assert decision.followup_confidence == 0.9


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf"), "0.8", True, None])
def test_invalid_probability(value):
    with pytest.raises(ValueError):
        parse_response(response_body(probability=value), QUESTION)


@pytest.mark.parametrize("mutation", ["missing", "unknown", "distribution", "confidence", "type"])
def test_invalid_fields(mutation):
    body = copy.deepcopy(response_body())
    if mutation == "missing":
        del body["answers"]["target"]
    elif mutation == "unknown":
        body["answers"]["target"]["choice"] = "point_999"
    elif mutation == "distribution":
        body["answers"]["relevance"]["probabilities"]["relevant"] = 0.2
    elif mutation == "confidence":
        body["answers"]["relevance"]["confidence"] = -1
    else:
        body["answers"]["followup"]["type"] = "choice"
    with pytest.raises((ValueError, KeyError)):
        parse_response(body, QUESTION)


async def test_http_contract_and_close(settings):
    from pydantic import SecretStr
    settings.jev_api_key = SecretStr("unit-secret")
    def handler(request):
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["authorization"] == "Bearer unit-secret"
        assert json.loads(request.content)["model"] == "jev-latest"
        return httpx.Response(200, json=response_body())
    client = JevDecisionClient(settings, transport=httpx.MockTransport(handler))
    try:
        decision = await client.assess_answer(question=QUESTION, turns=TURNS, followup_count=0)
        assert decision.followup_target == "point_1"
    finally:
        await client.close()
    assert client.http.is_closed


@pytest.mark.parametrize("scenario,reason", [
    ("timeout", "jev_timeout"), ("deadline", "jev_timeout"),
    ("network", "jev_network_error"), ("401", "jev_http_401"),
    ("429", "jev_http_429"), ("503", "jev_http_503"),
    ("json", "jev_invalid_response"), ("shape", "jev_invalid_response"),
])
async def test_http_failures(settings, scenario, reason):
    from pydantic import SecretStr
    settings.jev_api_key = SecretStr("unit-secret")
    settings.jev_timeout_seconds = 0.01
    async def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("private upstream message")
        if scenario == "deadline":
            await asyncio.sleep(0.1)
        if scenario == "network":
            raise httpx.ConnectError("private upstream message")
        if scenario.isdigit():
            return httpx.Response(int(scenario), text="private upstream message")
        return httpx.Response(200, text="not-json" if scenario == "json" else "{}")
    client = JevDecisionClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DecisionServiceError) as caught:
            await client.assess_answer(question=QUESTION, turns=TURNS, followup_count=0)
        assert caught.value.reason == reason
        assert "private" not in str(caught.value)
    finally:
        await client.close()


async def test_missing_key_makes_no_request(settings):
    def handler(request):
        pytest.fail("must not send a request without credentials")
    client = JevDecisionClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DecisionServiceError, match="回答诊断") as caught:
            await client.assess_answer(question=QUESTION, turns=TURNS, followup_count=0)
        assert caught.value.reason == "jev_missing_key"
    finally:
        await client.close()
