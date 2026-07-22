"""Deterministic scoring rubric and aggregation."""

from enum import StrEnum
from typing import Final


class DimensionCode(StrEnum):
    FOUNDATION = "foundation"
    ENGINEERING = "engineering"
    SYSTEM_DESIGN = "system_design"
    PROBLEM_SOLVING = "problem_solving"
    COMMUNICATION = "communication"


DIMENSION_WEIGHTS: Final[dict[DimensionCode, float]] = {
    DimensionCode.FOUNDATION: 0.20,
    DimensionCode.ENGINEERING: 0.25,
    DimensionCode.SYSTEM_DESIGN: 0.25,
    DimensionCode.PROBLEM_SOLVING: 0.20,
    DimensionCode.COMMUNICATION: 0.10,
}


DIMENSION_LABELS: Final[dict[DimensionCode, tuple[str, str]]] = {
    DimensionCode.FOUNDATION: ("基础知识准确性", "基础知识"),
    DimensionCode.ENGINEERING: ("Agent 工程实践", "工程实践"),
    DimensionCode.SYSTEM_DESIGN: ("系统设计与边界意识", "系统设计"),
    DimensionCode.PROBLEM_SOLVING: ("分析、取舍与问题解决", "问题解决"),
    DimensionCode.COMMUNICATION: ("技术表达", "表达逻辑"),
}


def score_0_to_100(score_0_to_5: float) -> float:
    return round(max(0.0, min(5.0, score_0_to_5)) * 20, 2)


def weighted_total(scores: dict[DimensionCode, float | None]) -> float | None:
    if any(scores.get(code) is None for code in DIMENSION_WEIGHTS):
        return None
    total = sum(float(scores[code]) * weight for code, weight in DIMENSION_WEIGHTS.items())
    return round(total, 2)

