"""Validated command bodies from the version 1 API contract."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.interview import Difficulty, FocusCode


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateInterviewRequest(StrictRequest):
    position_code: Literal["ai_agent_development"]
    focus_code: FocusCode
    difficulty: Difficulty
    rules_version: str
    rules_confirmed: bool


class StartInterviewRequest(StrictRequest):
    expected_row_version: int = Field(ge=1)


class SubmitAnswerRequest(StrictRequest):
    interrupt_id: str = Field(min_length=1)
    answer_to_turn_id: str = Field(min_length=1)
    content: str
    expected_row_version: int = Field(ge=1)


class FinishInterviewRequest(StrictRequest):
    reason: Literal["USER_REQUESTED"]
    confirm_partial_report: bool
    expected_row_version: int = Field(ge=1)


class RetryInterviewRequest(StrictRequest):
    failed_operation_id: str = Field(min_length=1)
    expected_row_version: int = Field(ge=1)
