"""Exercise decision routing through HTTP, SQLite, SSE and graph interrupts."""

import sqlite3

import httpx
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.decision.client import DecisionServiceError, JevDecisionClient
from app.decision.schemas import AnswerDecision
from app.llm.schemas import AnswerAssessment
from app.main import create_app
from tests.fakes import FakeInterviewLLM, FailOnceAssessmentLLM
from tests.test_interview_flows import _complete_interview, _create, _events, _key, _snapshot


class CountingLLM(FakeInterviewLLM):
    def __init__(self):
        self.assessments = 0
        self.followup_prompts = []

    async def complete_json(self, messages, schema, **kwargs):
        if schema is AnswerAssessment:
            self.assessments += 1
        return await super().complete_json(messages, schema, **kwargs)

    async def stream(self, messages, **kwargs):
        if "唯一追问重点" in messages[-1]["content"]:
            self.followup_prompts.append(messages[-1]["content"])
        async for chunk in super().stream(messages, **kwargs):
            yield chunk


class FakeDecision:
    def __init__(self, mode="followup"):
        self.mode = mode
        self.calls = []

    async def assess_answer(self, *, question, turns, followup_count):
        self.calls.append((question, turns, followup_count))
        if self.mode.startswith("jev_"):
            raise DecisionServiceError(self.mode)
        probability = 0.9 if followup_count == 0 or self.mode == "always" else 0.1
        if self.mode == "gray":
            probability = 0.5
        return AnswerDecision(
            answer_relevance="partially_relevant", followup_probability=probability,
            followup_confidence=0.2 if self.mode == "low" else 0.9,
            followup_target="point_0" if probability >= 0.5 else None,
        )


def test_jev_full_flow(settings):
    settings.decision_provider = "jev"
    decision, llm = FakeDecision(), CountingLLM()
    app = create_app(settings=settings, llm=llm, decision=decision)
    with TestClient(app) as client:
        report, events = _complete_interview(client, "[GOOD]")
        assert len([e for e in events if e["data"]["event"] == "answer.accepted"]) == 10
        assert all(q["followup_count"] == 1 for q in report["question_reviews"])
    assert llm.assessments == 0
    assert len(decision.calls) == 10
    assert len(llm.followup_prompts) == 5
    for prompt, (question, _, count) in zip(llm.followup_prompts, decision.calls[::2]):
        assert count == 0
        assert question["rubric_points"]["key_points"][0] in prompt
    with sqlite3.connect(settings.app_db_path) as db:
        rows = db.execute("SELECT role, kind, followup_level FROM interview_turns").fetchall()
    assert len([r for r in rows if r[0] == "candidate"]) == 10
    assert len([r for r in rows if r[1] == "followup"]) == 5


@pytest.mark.parametrize("mode", ["gray", "low", "jev_timeout", "jev_http_503", "jev_invalid_response"])
def test_fallback_preserves_interview(settings, mode, caplog):
    settings.decision_provider = "jev"
    decision, llm = FakeDecision(mode), CountingLLM()
    with caplog.at_level("INFO"), TestClient(create_app(settings=settings, llm=llm, decision=decision)) as client:
        report, _ = _complete_interview(client, "[BAD]")
    assert report["completeness"] == "FULL"
    assert llm.assessments == 10
    assert "deepseek_fallback" in caplog.text
    assert '"route_result": "fallback"' in caplog.text


@pytest.mark.parametrize("mode", ["always", "jev_timeout"])
def test_shadow_preserves_deepseek(settings, mode, caplog):
    settings.decision_provider = "jev"
    settings.jev_shadow_mode = True
    llm, decision = CountingLLM(), FakeDecision(mode)
    with caplog.at_level("INFO"), TestClient(create_app(settings=settings, llm=llm, decision=decision)) as client:
        report, _ = _complete_interview(client, "[GOOD]")
    assert all(q["followup_count"] == 0 for q in report["question_reviews"])
    assert llm.assessments == 5
    assert len(decision.calls) == 5
    assert "decision_shadow" in caplog.text


def test_limit_skips_provider(settings):
    settings.decision_provider = "jev"
    decision = FakeDecision("always")
    with TestClient(create_app(settings=settings, llm=CountingLLM(), decision=decision)) as client:
        report, _ = _complete_interview(client, "[GOOD]")
    assert all(q["followup_count"] == 2 for q in report["question_reviews"])
    assert all(count < 2 for _, _, count in decision.calls)
    assert len(decision.calls) == 10


def start(client):
    created = _create(client)
    _events(client.post(f"/api/v1/interviews/{created['id']}/start/stream",
        headers={"Idempotency-Key": _key()}, json={"expected_row_version": created["row_version"]}))
    return created["id"]


def answer(client, interview_id):
    snapshot = _snapshot(client, interview_id)
    pending = snapshot["pending_answer"]
    return _events(client.post(f"/api/v1/interviews/{interview_id}/answers/stream",
        headers={"Idempotency-Key": _key()}, json={
            "interrupt_id": pending["interrupt_id"], "answer_to_turn_id": pending["answer_to_turn_id"],
            "content": "我会使用 checkpoint 保存状态，并使用幂等的恢复逻辑。",
            "expected_row_version": snapshot["row_version"],
        }))


def test_jev_interrupt_survives_restart(settings):
    settings.decision_provider = "jev"
    with TestClient(create_app(settings=settings, llm=CountingLLM(), decision=FakeDecision())) as client:
        interview_id = start(client)
        answer(client, interview_id)
        before = _snapshot(client, interview_id)
        assert before["status"] == "WAITING_ANSWER"
    with TestClient(create_app(settings=settings, llm=CountingLLM(), decision=FakeDecision())) as client:
        assert _snapshot(client, interview_id)["pending_answer"] == before["pending_answer"]
        answer(client, interview_id)
        after = _snapshot(client, interview_id)
        assert after["status"] == "WAITING_ANSWER"
        assert after["pending_answer"]["answer_to_turn_id"] != before["pending_answer"]["answer_to_turn_id"]


def test_fallback_failure_can_retry(settings):
    settings.decision_provider = "jev"
    decision = FakeDecision("jev_timeout")
    with TestClient(create_app(settings=settings, llm=FailOnceAssessmentLLM(), decision=decision)) as client:
        interview_id = start(client)
        answer(client, interview_id)
        failed = _snapshot(client, interview_id)
        assert failed["status"] == "FAILED"
        error = failed["last_error"]
        _events(client.post(f"/api/v1/interviews/{interview_id}/retry/stream",
            headers={"Idempotency-Key": _key()}, json={
                "failed_operation_id": error["failed_operation_id"],
                "expected_row_version": failed["row_version"],
            }))
        assert _snapshot(client, interview_id)["status"] == "WAITING_ANSWER"
        assert len(decision.calls) == 1


def test_real_adapter_invalid_response_falls_back(settings):
    settings.decision_provider = "jev"
    settings.jev_api_key = SecretStr("unit-secret")
    llm = CountingLLM()
    adapter = JevDecisionClient(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {}})))
    with TestClient(create_app(settings=settings, llm=llm, decision=adapter)) as client:
        report, _ = _complete_interview(client, "[GOOD]")
        client.portal.call(adapter.close)
    assert report["completeness"] == "FULL"
    assert llm.assessments == 5


def test_disabled_fallback_is_recoverable(settings):
    settings.decision_provider = "jev"
    settings.jev_fallback_enabled = False
    llm = CountingLLM()
    with TestClient(create_app(settings=settings, llm=llm, decision=FakeDecision("gray"))) as client:
        interview_id = start(client)
        answer(client, interview_id)
        snapshot = _snapshot(client, interview_id)
        assert snapshot["status"] == "FAILED"
        assert snapshot["last_error"]["recoverable"] is True
    assert llm.assessments == 0


def test_deepseek_switch_does_not_call_jev(settings):
    decision = FakeDecision("always")
    with TestClient(create_app(settings=settings, llm=CountingLLM(), decision=decision)) as client:
        report, _ = _complete_interview(client, "[GOOD]")
    assert decision.calls == []
    assert all(q["followup_count"] == 0 for q in report["question_reviews"])
