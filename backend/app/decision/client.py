"""Bounded asynchronous TypeSafe HTTP adapter and generation baseline."""

import asyncio
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.core.errors import AppError
from app.core.settings import Settings
from app.decision.assessment import build_request, parse_response
from app.decision.schemas import AnswerDecision
from app.llm.client import InterviewLLM
from app.llm.prompts import assessment_messages
from app.llm.schemas import AnswerAssessment


class DecisionServiceError(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("ASSESSMENT_FAILED", "回答诊断服务暂时不可用", status_code=503,
                         recoverable=True)
        self.reason = reason


class DecisionClient(Protocol):
    async def assess_answer(self, *, question: dict[str, Any],
                            turns: list[dict[str, Any]], followup_count: int) -> AnswerDecision: ...


class DeepSeekAssessmentClient:
    def __init__(self, llm: InterviewLLM) -> None:
        self.llm = llm

    async def assess_answer(self, *, question: dict[str, Any],
                            turns: list[dict[str, Any]], followup_count: int) -> AnswerAssessment:
        return await self.llm.complete_json(
            assessment_messages(question, turns, followup_count), AnswerAssessment, max_tokens=900,
        )


class JevDecisionClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=settings.jev_timeout_seconds, transport=transport,
                                     follow_redirects=False)

    async def assess_answer(self, *, question: dict[str, Any],
                            turns: list[dict[str, Any]], followup_count: int) -> AnswerDecision:
        key = self.settings.jev_api_key.get_secret_value()
        if not key.strip():
            raise DecisionServiceError("jev_missing_key")
        try:
            body = build_request(question, turns, followup_count, self.settings.jev_model)
            # Bound total elapsed time, not only each individual HTTP operation.
            async with asyncio.timeout(self.settings.jev_timeout_seconds):
                response = await self.http.post(
                    self.settings.jev_base_url + "/v1/systemone", json=body,
                    headers={"Authorization": f"Bearer {key}"},
                )
                response.raise_for_status()
                return parse_response(response.json(), question)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise DecisionServiceError("jev_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise DecisionServiceError(f"jev_http_{exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise DecisionServiceError("jev_network_error") from exc
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            raise DecisionServiceError("jev_invalid_response") from exc

    async def close(self) -> None:
        await self.http.aclose()
