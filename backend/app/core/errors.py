"""Stable application errors mapped to the public API contract."""

from collections.abc import Sequence
from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        recoverable: bool = False,
        details: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.recoverable = recoverable
        self.details = list(details or [])


class LLMServiceError(AppError):
    pass


def not_found(interview_id: str) -> AppError:
    return AppError(
        "INTERVIEW_NOT_FOUND",
        "面试会话不存在",
        status_code=404,
        details=[{"interview_id": interview_id}],
    )

