"""Evidence validation and deterministic per-question score calculation."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.domain.rubric import DimensionCode, score_0_to_100
from app.llm.schemas import EvidenceItem, QuestionEvaluation


def validate_evaluation(
    evaluation: QuestionEvaluation,
    question: dict[str, Any],
    turns: list[dict[str, Any]],
) -> tuple[float, list[EvidenceItem]]:
    candidate_turns = {
        turn["id"]: turn["content"]
        for turn in turns
        if turn["role"] == "candidate" and turn["kind"] == "answer"
    }
    target_codes = {DimensionCode(code) for code in question["dimension_targets"]}
    missing_scores = target_codes - set(evaluation.dimension_scores)
    if missing_scores:
        raise AppError(
            "ASSESSMENT_FAILED",
            "评分结果缺少目标维度",
            status_code=503,
            recoverable=True,
            details=[{"missing_dimensions": sorted(code.value for code in missing_scores)}],
        )

    valid_evidence: list[EvidenceItem] = []
    evidence_dimensions: set[DimensionCode] = set()
    for item in evaluation.evidence:
        source = candidate_turns.get(item.turn_id)
        if source is None or item.quote not in source:
            raise AppError(
                "ASSESSMENT_FAILED",
                "评分证据无法映射到候选人回答",
                status_code=503,
                recoverable=True,
                details=[{"turn_id": item.turn_id, "dimension": item.dimension_code.value}],
            )
        if item.dimension_code in target_codes and item.dimension_code not in evidence_dimensions:
            valid_evidence.append(item)
            evidence_dimensions.add(item.dimension_code)
    missing_evidence = target_codes - evidence_dimensions
    if missing_evidence:
        raise AppError(
            "ASSESSMENT_FAILED",
            "评分结果缺少可回溯证据",
            status_code=503,
            recoverable=True,
            details=[{"missing_dimensions": sorted(code.value for code in missing_evidence)}],
        )

    weighted = 0.0
    weight_total = 0.0
    for raw_code, weight in question["dimension_targets"].items():
        code = DimensionCode(raw_code)
        weighted += score_0_to_100(evaluation.dimension_scores[code]) * float(weight)
        weight_total += float(weight)
    return round(weighted / weight_total, 2), valid_evidence

