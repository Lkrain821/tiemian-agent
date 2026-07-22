"""The only module allowed to call the DeepSeek OpenAI-compatible API."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, Protocol, TypeVar

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel

from app.core.errors import LLMServiceError
from app.core.settings import Settings


logger = logging.getLogger(__name__)
StructuredT = TypeVar("StructuredT", bound=BaseModel)
ReturnT = TypeVar("ReturnT")
Message = dict[str, str]


class InterviewLLM(Protocol):
    model_name: str

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str: ...

    def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> AsyncIterator[str]: ...

    async def complete_json(
        self,
        messages: Sequence[Message],
        schema: type[StructuredT],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> StructuredT: ...

    async def healthcheck(self) -> bool: ...


class DeepSeekClient:
    """Centralized DeepSeek adapter with explicit retry and error mapping."""

    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.deepseek_model
        self._max_retries = settings.deepseek_max_retries
        self._thinking_mode = settings.deepseek_thinking_mode
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            timeout=settings.deepseek_timeout_seconds,
            max_retries=0,
        )

    def _extra_body(self) -> dict[str, Any]:
        return {"thinking": {"type": self._thinking_mode}}

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        async def request() -> str:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=list(messages),  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=self._extra_body(),
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMServiceError(
                    "QUESTION_GENERATION_FAILED",
                    "模型返回了空内容",
                    status_code=503,
                    recoverable=True,
                )
            return content

        return await self._retry(request)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> AsyncIterator[str]:
        for attempt in range(self._max_retries + 1):
            emitted = False
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=list(messages),  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    extra_body=self._extra_body(),
                )
                async for chunk in response:
                    text = chunk.choices[0].delta.content if chunk.choices else None
                    if text:
                        emitted = True
                        yield text
                if not emitted:
                    raise LLMServiceError(
                        "QUESTION_GENERATION_FAILED",
                        "模型流式响应为空",
                        status_code=503,
                        recoverable=True,
                    )
                return
            except asyncio.CancelledError:
                raise
            except LLMServiceError:
                raise
            except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as exc:
                if emitted or attempt >= self._max_retries:
                    raise self._map_error(exc) from exc
                await self._backoff(attempt)
            except APIError as exc:
                raise self._map_error(exc) from exc

    async def complete_json(
        self,
        messages: Sequence[Message],
        schema: type[StructuredT],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> StructuredT:
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        json_messages = [
            *messages,
            {
                "role": "system",
                "content": f"Return json only. The JSON must satisfy this schema: {schema_text}",
            },
        ]

        async def request() -> StructuredT:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=json_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMServiceError(
                    "ASSESSMENT_FAILED",
                    "模型结构化响应为空",
                    status_code=503,
                    recoverable=True,
                )
            try:
                return schema.model_validate_json(content)
            except (ValueError, json.JSONDecodeError) as exc:
                raise LLMServiceError(
                    "ASSESSMENT_FAILED",
                    "模型结构化响应校验失败",
                    status_code=503,
                    recoverable=True,
                    details=[{"reason": "schema_validation"}],
                ) from exc

        return await self._retry(request)

    async def healthcheck(self) -> bool:
        try:
            models = await self._client.models.list()
        except (APIError, APIConnectionError, APITimeoutError):
            return False
        return any(model.id == self.model_name for model in models.data)

    async def close(self) -> None:
        await self._client.close()

    async def _retry(self, operation: Callable[[], Awaitable[ReturnT]]) -> ReturnT:
        for attempt in range(self._max_retries + 1):
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except LLMServiceError:
                raise
            except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as exc:
                if attempt >= self._max_retries:
                    raise self._map_error(exc) from exc
                await self._backoff(attempt)
            except APIError as exc:
                raise self._map_error(exc) from exc
        raise AssertionError("unreachable")

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(min(0.5 * (2**attempt), 4.0))

    @staticmethod
    def _map_error(exc: APIError) -> LLMServiceError:
        if isinstance(exc, APITimeoutError):
            return LLMServiceError(
                "LLM_TIMEOUT",
                "面试官响应超时，可重试当前步骤",
                status_code=504,
                recoverable=True,
            )
        if isinstance(exc, RateLimitError):
            return LLMServiceError(
                "LLM_RATE_LIMITED",
                "模型服务暂时限流，请稍后重试",
                status_code=503,
                recoverable=True,
            )
        return LLMServiceError(
            "QUESTION_GENERATION_FAILED",
            "模型服务暂时不可用",
            status_code=503,
            recoverable=True,
        )
