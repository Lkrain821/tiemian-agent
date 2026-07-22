"""JSON-serializable LangGraph state for interview_v1."""

from typing import Any, TypedDict


class InterviewState(TypedDict, total=False):
    session_id: str
    graph_version: str
    position_direction: str
    focus: str
    difficulty: str
    target_question_count: int
    max_followups: int
    question_blueprint: list[dict[str, str]]
    used_question_ids: list[str]
    used_variant_groups: list[str]
    used_fingerprints: list[str]
    selected_question: dict[str, Any] | None
    current_question: dict[str, Any] | None
    current_question_no: int
    completed_question_count: int
    current_followup_count: int
    current_turns: list[dict[str, Any]]
    pending_prompt: dict[str, Any] | None
    pending_input: dict[str, Any] | None
    input_valid: bool
    validation_error: dict[str, Any] | None
    answer_assessment: dict[str, Any] | None
    question_evaluation: dict[str, Any] | None
    question_results: list[dict[str, Any]]
    finish_requested: bool
    finish_reason: str | None
    report: dict[str, Any] | None
    status: str
    failure: dict[str, Any] | None

