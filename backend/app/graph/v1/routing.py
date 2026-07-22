"""Deterministic conditional-edge routing for interview_v1."""

from app.graph.v1.state import InterviewState


def route_input(state: InterviewState) -> str:
    pending = state.get("pending_input") or {}
    return "finish" if pending.get("type") == "finish" else "answer"


def route_validation(state: InterviewState) -> str:
    return "valid" if state.get("input_valid") else "invalid"


def route_assessment(state: InterviewState) -> str:
    assessment = state.get("answer_assessment") or {}
    if assessment.get("followup_needed") and state.get("current_followup_count", 0) < state.get(
        "max_followups", 2
    ):
        return "followup"
    return "score"


def route_next_question(state: InterviewState) -> str:
    if state.get("completed_question_count", 0) < state.get("target_question_count", 5):
        return "next"
    return "report"

