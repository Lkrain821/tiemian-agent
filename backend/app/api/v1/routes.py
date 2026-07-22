"""Version 1 REST and POST-SSE routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import get_container, get_request_id
from app.api.schemas.common import ApiResponse
from app.api.schemas.interviews import (
    CreateInterviewRequest,
    FinishInterviewRequest,
    RetryInterviewRequest,
    StartInterviewRequest,
    SubmitAnswerRequest,
)
from app.application.container import ApplicationContainer
from app.application.commands import PreparedStream
from app.core.errors import AppError
from app.core.time import utc_now_iso


router = APIRouter(prefix="/api/v1")
Container = Annotated[ApplicationContainer, Depends(get_container)]
RequestId = Annotated[str, Depends(get_request_id)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def success(message: str, request_id: str, **data: object) -> ApiResponse:
    return ApiResponse(code="OK", message=message, data={"request_id": request_id, **data})


def required_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "请求必须携带 Idempotency-Key",
            status_code=400,
            recoverable=True,
        )
    return value.strip()


@router.get("/interview-options", response_model=ApiResponse)
async def interview_options(container: Container, request_id: RequestId) -> ApiResponse:
    return success("获取面试配置成功", request_id, **container.queries.options())


@router.get("/health/live", response_model=ApiResponse)
async def health_live(container: Container, request_id: RequestId) -> ApiResponse:
    return success(
        "服务存活",
        request_id,
        status="UP",
        service="tiemian-api",
        api_version=container.settings.api_version,
        checked_at=utc_now_iso(),
    )


@router.get("/health/ready", response_model=ApiResponse)
async def health_ready(
    container: Container, request_id: RequestId, response: Response
) -> ApiResponse:
    checks = {
        "business_database": "UP" if await container.database.ping() else "DOWN",
        "checkpoint_database": (
            "UP" if container.settings.checkpoint_db_path.exists() else "DOWN"
        ),
        "question_bank": "UP" if container.question_bank.counts()["total"] == 30 else "DOWN",
        "llm_configuration": (
            "UP"
            if container.settings.deepseek_api_key.get_secret_value()
            and container.settings.deepseek_model
            and container.settings.deepseek_base_url
            else "DOWN"
        ),
    }
    if any(value != "UP" for value in checks.values()):
        response.status_code = 503
        return ApiResponse(
            code="SERVICE_NOT_READY",
            message="模拟面试系统暂未就绪",
            data={
                "request_id": request_id,
                "recoverable": True,
                "details": [
                    {"component": name, "reason": "resource_unavailable"}
                    for name, value in checks.items()
                    if value != "UP"
                ],
            },
        )
    return success(
        "模拟面试系统已就绪",
        request_id,
        status="READY",
        checks=checks,
        checked_at=utc_now_iso(),
    )


@router.post("/interviews", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    body: CreateInterviewRequest,
    response: Response,
    container: Container,
    request_id: RequestId,
    idempotency_key: IdempotencyKey = None,
) -> ApiResponse:
    data, created = await container.commands.create_interview(
        body, required_key(idempotency_key), request_id
    )
    if not created:
        response.status_code = 200
    return ApiResponse(code="OK", message="面试会话创建成功", data=data)


@router.get("/interviews", response_model=ApiResponse)
async def list_interviews(
    container: Container,
    request_id: RequestId,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ApiResponse:
    return success(
        "获取历史面试记录成功",
        request_id,
        **await container.queries.history(page=page, page_size=page_size),
    )


@router.get("/interviews/{interview_id}", response_model=ApiResponse)
async def get_interview(
    interview_id: str, container: Container, request_id: RequestId
) -> ApiResponse:
    return success(
        "获取面试会话成功",
        request_id,
        interview=await container.queries.snapshot(interview_id),
    )


async def prepare_start_stream(
    interview_id: str,
    body: StartInterviewRequest,
    container: Container,
    idempotency_key: IdempotencyKey = None,
) -> PreparedStream:
    return await container.commands.prepare_start(
        interview_id, body, required_key(idempotency_key)
    )


@router.post("/interviews/{interview_id}/start/stream", response_class=EventSourceResponse)
async def start_interview(
    prepared: Annotated[PreparedStream, Depends(prepare_start_stream)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in prepared.events:
        yield event


async def prepare_answer_stream(
    interview_id: str,
    body: SubmitAnswerRequest,
    container: Container,
    idempotency_key: IdempotencyKey = None,
) -> PreparedStream:
    return await container.commands.prepare_answer(
        interview_id, body, required_key(idempotency_key)
    )


@router.post("/interviews/{interview_id}/answers/stream", response_class=EventSourceResponse)
async def submit_answer(
    prepared: Annotated[PreparedStream, Depends(prepare_answer_stream)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in prepared.events:
        yield event


async def prepare_finish_stream(
    interview_id: str,
    body: FinishInterviewRequest,
    container: Container,
    idempotency_key: IdempotencyKey = None,
) -> PreparedStream:
    return await container.commands.prepare_finish(
        interview_id, body, required_key(idempotency_key)
    )


@router.post("/interviews/{interview_id}/finish/stream", response_class=EventSourceResponse)
async def finish_interview(
    prepared: Annotated[PreparedStream, Depends(prepare_finish_stream)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in prepared.events:
        yield event


async def prepare_retry_stream(
    interview_id: str,
    body: RetryInterviewRequest,
    container: Container,
    idempotency_key: IdempotencyKey = None,
) -> PreparedStream:
    return await container.commands.prepare_retry(
        interview_id, body, required_key(idempotency_key)
    )


@router.post("/interviews/{interview_id}/retry/stream", response_class=EventSourceResponse)
async def retry_interview(
    prepared: Annotated[PreparedStream, Depends(prepare_retry_stream)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in prepared.events:
        yield event


@router.get("/interviews/{interview_id}/report", response_model=ApiResponse)
async def get_report(
    interview_id: str, container: Container, request_id: RequestId
) -> ApiResponse:
    return success(
        "获取面试报告成功",
        request_id,
        report=await container.queries.report(interview_id),
    )
