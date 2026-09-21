"""Deterministic conditional-edge routing for interview_v1."""

import json
import logging

from app.core.settings import Settings
from app.decision.client import DecisionServiceError
from app.graph.v1.state import InterviewState


logger = logging.getLogger(__name__)


def decision_route(assessment: dict, *, followup_threshold: float = 0.70,
                   score_threshold: float = 0.30, min_confidence: float = 0.60) -> tuple[str, str | None]:
    if assessment["followup_confidence"] < min_confidence:
        return "fallback", "low_confidence"
    probability = assessment["followup_probability"]
    if probability >= followup_threshold:
        if assessment["followup_target"] is None:
            return "fallback", "missing_followup_target"
        return "followup", None
    if probability <= score_threshold:
        return "score", None
    return "fallback", "probability_gray_zone"


def assessment_route(state: InterviewState, settings: Settings | None = None) -> tuple[str, str | None]:
    if state.get("current_followup_count", 0) >= state.get("max_followups", 2):
        return "score", None
    metadata = state.get("decision_metadata") or {}
    if metadata.get("fallback_reason"):
        return "fallback", metadata["fallback_reason"]
    assessment = state.get("answer_assessment") or {}
    if assessment.get("decision_source") == "jev":
        kwargs = {} if settings is None else {
            "followup_threshold": settings.jev_followup_threshold,
            "score_threshold": settings.jev_score_threshold,
            "min_confidence": settings.jev_min_confidence,
        }
        return decision_route(assessment, **kwargs)
    return route_fallback_assessment(state), None


def log_assessment(state: InterviewState, route: str, reason: str | None) -> None:
    assessment = state.get("answer_assessment") or {}
    logger.info("answer_decision %s", json.dumps({
        **(state.get("decision_metadata") or {}),
        "session_id": state.get("session_id"),
        "question_id": (state.get("current_question") or {}).get("id"),
        "followup_probability": assessment.get("followup_probability"),
        "confidence": assessment.get("followup_confidence"),
        "followup_target": assessment.get("followup_target"),
        "followup_needed": assessment.get("followup_needed"),
        "route_result": route, "fallback_reason": reason,
        "followup_count": state.get("current_followup_count", 0),
    }, ensure_ascii=False))


def route_input(state: InterviewState) -> str:
    pending = state.get("pending_input") or {}
    return "finish" if pending.get("type") == "finish" else "answer"


def route_validation(state: InterviewState) -> str:
    return "valid" if state.get("input_valid") else "invalid"


def route_assessment(state: InterviewState, settings: Settings | None = None) -> str:
    route, reason = assessment_route(state, settings)
    log_assessment(state, route, reason)
    if route == "fallback" and settings is not None and not settings.jev_fallback_enabled:
        raise DecisionServiceError(reason or "jev_uncertain")
    return route


def route_fallback_assessment(state: InterviewState) -> str:
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
