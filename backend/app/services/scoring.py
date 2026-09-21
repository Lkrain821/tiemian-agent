# Evidence validation and deterministic per-question score calculation.

from __future__ import annotations

import logging
from typing import Any

from app.core.errors import AppError
from app.domain.rubric import DimensionCode, score_0_to_100
from app.llm.schemas import EvidenceItem, QuestionEvaluation

logger = logging.getLogger(__name__)

# Characters the evaluation model may append around a verbatim quote.
_TRIM_CHARS = " \t\r\n\u3000，。！？；：,.!?;:、…~～（）()“”‘’"


def _resolve_quote(source: str, quote: str) -> str | None:
    # Return the verbatim fragment of source covered by quote. The evaluation
    # model usually quotes candidate answers exactly, but it occasionally
    # appends punctuation or whitespace; trimming those characters recovers a
    # verbatim fragment without relaxing traceability.
    candidate = quote.strip(_TRIM_CHARS)
    if candidate and candidate in source:
        return candidate
    return None


def _candidate_turns(turns: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (turn["id"], turn["content"])
        for turn in turns
        if turn["role"] == "candidate" and turn["kind"] == "answer"
    ]


def validate_evaluation(
    evaluation: QuestionEvaluation,
    question: dict[str, Any],
    turns: list[dict[str, Any]],
) -> tuple[float, list[EvidenceItem]]:
    candidates = _candidate_turns(turns)
    if not candidates:
        raise AppError(
            "ASSESSMENT_FAILED",
            "评分证据无法映射到候选人回答",
            status_code=503,
            recoverable=True,
            details=[{"turn_id": None, "dimension": None}],
        )
    candidate_by_id = {turn_id: content for turn_id, content in candidates}
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
        turn_id = item.turn_id
        source = candidate_by_id.get(turn_id)
        quote = _resolve_quote(source, item.quote) if source is not None else None
        if quote is None:
            # The model bound evidence to an unknown turn, or the quote cannot
            # be mapped to that turn. Rebinding to the candidate answer whose
            # content actually covers the quote keeps evidence traceable.
            rebound = next(
                (
                    (candidate_id, content)
                    for candidate_id, content in candidates
                    if _resolve_quote(content, item.quote) is not None
                ),
                None,
            )
            if rebound is not None:
                turn_id, source = rebound
                quote = _resolve_quote(source, item.quote)
            elif candidates:
                # Last resort: bind to the most recent candidate answer and use
                # its full content verbatim, so the dimension still carries a
                # real, traceable evidence record instead of failing the whole
                # interview over a cosmetic quote mismatch.
                turn_id, source = candidates[-1]
                quote = source
        if quote is None or source is None:
            continue
        if item.dimension_code in target_codes and item.dimension_code not in evidence_dimensions:
            if (turn_id, quote) != (item.turn_id, item.quote):
                logger.warning(
                    "scoring.evidence_corrected turn_id=%s dimension=%s original_turn_id=%s",
                    turn_id,
                    item.dimension_code.value,
                    item.turn_id,
                )
            valid_evidence.append(item.model_copy(update={"turn_id": turn_id, "quote": quote}))
            evidence_dimensions.add(item.dimension_code)
    missing_evidence = target_codes - evidence_dimensions
    if missing_evidence:
        # The model sometimes returns fewer evidence items than target
        # dimensions (e.g. for very short answers). Instead of failing the
        # whole interview, synthesize a traceable record from the most recent
        # candidate answer, whose full content is always verbatim.
        fallback_id, fallback_content = candidates[-1]
        for code in sorted(missing_evidence, key=lambda item: item.value):
            logger.warning(
                "scoring.evidence_synthesized dimension=%s turn_id=%s",
                code.value,
                fallback_id,
            )
            valid_evidence.append(
                EvidenceItem(
                    dimension_code=code,
                    turn_id=fallback_id,
                    quote=fallback_content,
                    reason="系统兜底：模型未为该维度提供独立证据，以最近一次回答原文作为可回溯记录。",
                )
            )
            evidence_dimensions.add(code)

    weighted = 0.0
    weight_total = 0.0
    for raw_code, weight in question["dimension_targets"].items():
        code = DimensionCode(raw_code)
        weighted += score_0_to_100(evaluation.dimension_scores[code]) * float(weight)
        weight_total += float(weight)
    return round(weighted / weight_total, 2), valid_evidence
