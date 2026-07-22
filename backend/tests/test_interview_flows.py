"""End-to-end API simulations for good, weak, and off-topic answers."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from tests.fakes import FailOnceAssessmentLLM, FakeInterviewLLM


def _key() -> str:
    return str(uuid4())


def _events(response) -> list[dict]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _create(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/interviews",
        headers={"Idempotency-Key": _key()},
        json={
            "position_code": "ai_agent_development",
            "focus_code": "agent_application_engineering",
            "difficulty": "mid",
            "rules_version": "mvp-1",
            "rules_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["interview"]


def _snapshot(client: TestClient, interview_id: str) -> dict:
    response = client.get(f"/api/v1/interviews/{interview_id}")
    assert response.status_code == 200
    return response.json()["data"]["interview"]


def _complete_interview(client: TestClient, marker: str) -> tuple[dict, list[dict]]:
    created = _create(client)
    interview_id = created["id"]
    start = client.post(
        f"/api/v1/interviews/{interview_id}/start/stream",
        headers={"Idempotency-Key": _key(), "Accept": "text/event-stream"},
        json={"expected_row_version": created["row_version"]},
    )
    start_events = _events(start)
    assert start_events[0]["data"]["event"] == "stream.open"
    assert any(item["data"]["event"] == "question.changed" for item in start_events)
    assert start_events[-1]["data"]["event"] == "stream.done"

    all_events = list(start_events)
    answer_number = 0
    while True:
        snapshot = _snapshot(client, interview_id)
        if snapshot["status"] in {"COMPLETED", "PARTIAL"}:
            break
        assert snapshot["status"] == "WAITING_ANSWER"
        answer_number += 1
        pending = snapshot["pending_answer"]
        text = (
            f"{marker} 第 {answer_number} 次回答：我会先明确目标和基线，再分层检查数据、"
            "模型、工具和状态流转，用成功率、延迟、错误率做对照，最后设置幂等、超时和回退。"
        )
        response = client.post(
            f"/api/v1/interviews/{interview_id}/answers/stream",
            headers={"Idempotency-Key": _key(), "Accept": "text/event-stream"},
            json={
                "interrupt_id": pending["interrupt_id"],
                "answer_to_turn_id": pending["answer_to_turn_id"],
                "content": text,
                "expected_row_version": snapshot["row_version"],
            },
        )
        operation_events = _events(response)
        assert operation_events[0]["data"]["event"] == "stream.open"
        assert operation_events[1]["data"]["event"] == "answer.accepted"
        assert operation_events[-1]["data"]["event"] == "stream.done"
        all_events.extend(operation_events)
        assert answer_number <= 15

    report_response = client.get(f"/api/v1/interviews/{interview_id}/report")
    assert report_response.status_code == 200, report_response.text
    return report_response.json()["data"]["report"], all_events


@pytest.mark.parametrize(
    ("marker", "expected_answers", "expected_score"),
    [
        ("[GOOD]", 5, 90.0),
        ("[BAD]", 10, 44.0),
        ("[OFFTOPIC]", 15, 10.0),
    ],
)
def test_complete_interview_scenarios(
    client: TestClient, marker: str, expected_answers: int, expected_score: float
) -> None:
    report, events = _complete_interview(client, marker)
    accepted = [item for item in events if item["data"]["event"] == "answer.accepted"]

    assert len(accepted) == expected_answers
    assert report["completeness"] == "FULL"
    assert report["completion"]["completed_question_count"] == 5
    assert report["overall"]["total_score"] == expected_score
    assert len(report["dimensions"]) == 5
    assert len(report["question_reviews"]) == 5
    assert len(report["suggestions"]) == 3
    assert max(item["followup_count"] for item in report["question_reviews"]) <= 2


def test_options_health_and_api_errors(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json()["data"]["status"] == "UP"
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    options = client.get("/api/v1/interview-options").json()["data"]
    assert options["interview_spec"]["main_question_count"] == 5

    missing_key = client.post(
        "/api/v1/interviews",
        json={
            "position_code": "ai_agent_development",
            "focus_code": "agent_application_engineering",
            "difficulty": "mid",
            "rules_version": "mvp-1",
            "rules_confirmed": True,
        },
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_create_idempotency(client: TestClient) -> None:
    key = _key()
    body = {
        "position_code": "ai_agent_development",
        "focus_code": "rag_knowledge_application",
        "difficulty": "senior",
        "rules_version": "mvp-1",
        "rules_confirmed": True,
    }
    first = client.post("/api/v1/interviews", headers={"Idempotency-Key": key}, json=body)
    second = client.post("/api/v1/interviews", headers={"Idempotency-Key": key}, json=body)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["interview"]["id"] == second.json()["data"]["interview"]["id"]


def test_interrupt_checkpoint_survives_process_restart(settings: Settings) -> None:
    app = create_app(settings=settings, llm=FakeInterviewLLM())
    with TestClient(app) as first_client:
        created = _create(first_client)
        interview_id = created["id"]
        start_key = _key()
        first_events = _events(
            first_client.post(
                f"/api/v1/interviews/{interview_id}/start/stream",
                headers={"Idempotency-Key": start_key},
                json={"expected_row_version": created["row_version"]},
            )
        )
        assert first_events[-2]["data"]["event"] == "waiting.answer"
        before_restart = _snapshot(first_client, interview_id)

    restarted = create_app(settings=settings, llm=FakeInterviewLLM())
    with TestClient(restarted) as second_client:
        restored = _snapshot(second_client, interview_id)
        assert restored["pending_answer"] == before_restart["pending_answer"]
        pending = restored["pending_answer"]
        answer_key = _key()
        body = {
            "interrupt_id": pending["interrupt_id"],
            "answer_to_turn_id": pending["answer_to_turn_id"],
            "content": "[GOOD] 重启后继续回答，并说明指标、幂等和失败回退。",
            "expected_row_version": restored["row_version"],
        }
        first_answer = second_client.post(
            f"/api/v1/interviews/{interview_id}/answers/stream",
            headers={"Idempotency-Key": answer_key},
            json=body,
        )
        replayed_answer = second_client.post(
            f"/api/v1/interviews/{interview_id}/answers/stream",
            headers={"Idempotency-Key": answer_key},
            json=body,
        )
        assert _events(first_answer) == _events(replayed_answer)
        turns = _snapshot(second_client, interview_id)["messages"]
        matching = [item for item in turns if item["role"] == "candidate"]
        assert len(matching) == 1


def test_retry_resumes_failed_graph_step(settings: Settings) -> None:
    app = create_app(settings=settings, llm=FailOnceAssessmentLLM())
    with TestClient(app) as client:
        created = _create(client)
        interview_id = created["id"]
        _events(
            client.post(
                f"/api/v1/interviews/{interview_id}/start/stream",
                headers={"Idempotency-Key": _key()},
                json={"expected_row_version": created["row_version"]},
            )
        )
        waiting = _snapshot(client, interview_id)
        pending = waiting["pending_answer"]
        failed_events = _events(
            client.post(
                f"/api/v1/interviews/{interview_id}/answers/stream",
                headers={"Idempotency-Key": _key()},
                json={
                    "interrupt_id": pending["interrupt_id"],
                    "answer_to_turn_id": pending["answer_to_turn_id"],
                    "content": "[GOOD] 我会建立指标、对照实验和失败回退。",
                    "expected_row_version": waiting["row_version"],
                },
            )
        )
        assert failed_events[-2]["data"]["event"] == "error"
        failed = _snapshot(client, interview_id)
        assert failed["status"] == "FAILED"
        retry_events = _events(
            client.post(
                f"/api/v1/interviews/{interview_id}/retry/stream",
                headers={"Idempotency-Key": _key()},
                json={
                    "failed_operation_id": failed["last_error"]["failed_operation_id"],
                    "expected_row_version": failed["row_version"],
                },
            )
        )
        assert retry_events[-2]["data"]["event"] == "waiting.answer"
        recovered = _snapshot(client, interview_id)
        assert recovered["status"] == "WAITING_ANSWER"
        assert recovered["progress"]["completed_question_count"] == 1


def test_partial_report_does_not_invent_unfinished_reviews(client: TestClient) -> None:
    created = _create(client)
    interview_id = created["id"]
    _events(
        client.post(
            f"/api/v1/interviews/{interview_id}/start/stream",
            headers={"Idempotency-Key": _key()},
            json={"expected_row_version": created["row_version"]},
        )
    )
    snapshot = _snapshot(client, interview_id)
    finish = client.post(
        f"/api/v1/interviews/{interview_id}/finish/stream",
        headers={"Idempotency-Key": _key()},
        json={
            "reason": "USER_REQUESTED",
            "confirm_partial_report": True,
            "expected_row_version": snapshot["row_version"],
        },
    )
    _events(finish)
    report = client.get(f"/api/v1/interviews/{interview_id}/report").json()["data"]["report"]
    assert report["completeness"] == "PARTIAL"
    assert report["overall"]["total_score"] is None
    assert report["question_reviews"] == []
    assert report["completion"]["limitation_note"]


def test_history_lists_only_persisted_reports_with_stable_pagination(
    client: TestClient,
) -> None:
    active = _create(client)
    empty_history = client.get("/api/v1/interviews").json()["data"]
    assert empty_history["items"] == []
    assert empty_history["summary"] == {
        "total_count": 0,
        "full_count": 0,
        "partial_count": 0,
    }
    assert empty_history["pagination"]["total_pages"] == 0

    full_report, _ = _complete_interview(client, "[GOOD]")

    partial = _create(client)
    partial_id = partial["id"]
    _events(
        client.post(
            f"/api/v1/interviews/{partial_id}/start/stream",
            headers={"Idempotency-Key": _key()},
            json={"expected_row_version": partial["row_version"]},
        )
    )
    waiting = _snapshot(client, partial_id)
    _events(
        client.post(
            f"/api/v1/interviews/{partial_id}/finish/stream",
            headers={"Idempotency-Key": _key()},
            json={
                "reason": "USER_REQUESTED",
                "confirm_partial_report": True,
                "expected_row_version": waiting["row_version"],
            },
        )
    )

    first_page = client.get("/api/v1/interviews?page=1&page_size=1")
    second_page = client.get("/api/v1/interviews?page=2&page_size=1")
    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first_data = first_page.json()["data"]
    second_data = second_page.json()["data"]

    assert first_data["summary"] == {
        "total_count": 2,
        "full_count": 1,
        "partial_count": 1,
    }
    assert first_data["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total_items": 2,
        "total_pages": 2,
        "has_previous": False,
        "has_next": True,
    }
    assert second_data["pagination"]["has_previous"] is True
    assert second_data["pagination"]["has_next"] is False

    history_items = [first_data["items"][0], second_data["items"][0]]
    assert {item["interview_id"] for item in history_items} == {
        full_report["interview_id"],
        partial_id,
    }
    assert {item["completeness"] for item in history_items} == {"FULL", "PARTIAL"}
    assert all(item["report_url"].endswith("/report") for item in history_items)
    assert active["id"] not in {item["interview_id"] for item in history_items}

    partial_item = next(item for item in history_items if item["completeness"] == "PARTIAL")
    assert partial_item["overall"]["total_score"] is None
    assert partial_item["completion"]["completed_question_count"] == 0


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=51"])
def test_history_rejects_invalid_pagination(client: TestClient, query: str) -> None:
    response = client.get(f"/api/v1/interviews?{query}")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
