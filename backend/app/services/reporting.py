"""Deterministic report assembly from persisted scores and evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.time import parse_utc, utc_now_iso
from app.domain.interview import DIFFICULTY_LABELS, FOCUS_LABELS, Difficulty, FocusCode
from app.domain.rubric import DIMENSION_LABELS, DIMENSION_WEIGHTS, DimensionCode, score_0_to_100, weighted_total
from app.llm.schemas import ReportNarrative
from app.repositories.json_utils import loads


def report_context(
    session: dict[str, Any],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "config": {
            "focus": session["focus"],
            "difficulty": session["difficulty"],
            "completed_question_count": session["completed_question_count"],
            "target_question_count": session["target_question_count"],
        },
        "questions": [
            {
                "number": item["sequence_no"],
                "stem": item["stem"],
                "score": item["question_score"],
                "strengths": loads(item["strengths_json"], []),
                "gaps": loads(item["gaps_json"], []),
                "improvement": item["improvement"],
            }
            for item in evaluations
        ],
    }


async def build_report(
    *,
    session: dict[str, Any],
    evaluations: list[dict[str, Any]],
    dimension_rows: dict[str, list[dict[str, Any]]],
    narrative: ReportNarrative,
    partial_score_min_questions: int,
) -> dict[str, Any]:
    completeness = "FULL" if session["completed_question_count"] == session["target_question_count"] else "PARTIAL"
    sufficient = session["completed_question_count"] >= partial_score_min_questions

    dimension_values: dict[DimensionCode, list[float]] = defaultdict(list)
    for evaluation in evaluations:
        for row in dimension_rows.get(evaluation["id"], []):
            dimension_values[DimensionCode(row["dimension_code"])].append(
                score_0_to_100(float(row["score_0_to_5"]))
            )

    dimension_scores: dict[DimensionCode, float | None] = {}
    dimensions: list[dict[str, Any]] = []
    for code, weight in DIMENSION_WEIGHTS.items():
        values = dimension_values.get(code, [])
        score = round(sum(values) / len(values), 2) if sufficient and values else None
        dimension_scores[code] = score
        label, short_label = DIMENSION_LABELS[code]
        dimensions.append(
            {
                "code": code.value,
                "label": label,
                "short_label": short_label,
                "weight": weight,
                "score": score,
                "max_score": 100,
                "level_code": _level_code(score),
                "level_label": _level_label(score),
                "summary": _dimension_summary(code, score),
                "evidence_status": "SUFFICIENT" if score is not None else "INSUFFICIENT",
                "supported_question_count": len(values),
            }
        )

    total = weighted_total(dimension_scores) if sufficient else None
    started = parse_utc(session["started_at"])
    completed = parse_utc(session["completed_at"]) or parse_utc(utc_now_iso())
    duration = int((completed - started).total_seconds()) if started and completed else 0
    config_focus = FocusCode(session["focus"])
    config_difficulty = Difficulty(session["difficulty"])

    question_reviews = [
        {
            "question_id": item["question_instance_id"],
            "number": item["sequence_no"],
            "topic_code": item["topic_code"],
            "topic_label": item["topic_label"],
            "followup_count": item["followup_count"],
            "stem": item["stem"],
            "score": item["question_score"],
            "max_score": 100,
            "strengths": loads(item["strengths_json"], []),
            "gaps": loads(item["gaps_json"], []),
            "improvement": item["improvement"],
            "better_answer_outline": loads(item["better_answer_outline_json"], []),
            "evidence": [
                {"turn_id": row["evidence_turn_id"], "quote": row["evidence_quote"]}
                for row in dimension_rows.get(item["id"], [])[:2]
            ],
        }
        for item in evaluations
    ]

    suggestions = []
    priority_meta = [
        ("HIGHEST", "最高优先级", "预计 2–3 次专项练习"),
        ("ENGINEERING_DEPTH", "工程深化", "结合项目复盘"),
        ("COMMUNICATION_UPGRADE", "表达升级", "保持现有优势"),
    ]
    for index, suggestion in enumerate(narrative.suggestions, start=1):
        priority_code, priority_label, effort_label = priority_meta[index - 1]
        suggestions.append(
            {
                "priority": index,
                "priority_code": priority_code,
                "priority_label": priority_label,
                "effort_label": effort_label,
                "title": suggestion.title,
                "why": suggestion.why,
                "actions": suggestion.actions,
                "completion_criteria": suggestion.completion_criteria,
            }
        )

    limitation = None
    if completeness == "PARTIAL":
        limitation = (
            f"本报告只基于已完成的 {session['completed_question_count']} / "
            f"{session['target_question_count']} 道主问题，结论不代表完整能力画像。"
        )

    return {
        "id": session.get("report_id"),
        "interview_id": session["id"],
        "completeness": completeness,
        "generated_at": utc_now_iso(),
        "config": {
            "position_code": "ai_agent_development",
            "position_label": "AI Agent 开发",
            "focus_code": config_focus.value,
            "focus_label": FOCUS_LABELS[config_focus],
            "difficulty": config_difficulty.value,
            "difficulty_label": DIFFICULTY_LABELS[config_difficulty],
        },
        "completion": {
            "finish_reason": session.get("finish_reason") or (
                "ALL_QUESTIONS_COMPLETED" if completeness == "FULL" else "USER_REQUESTED"
            ),
            "completed_question_count": session["completed_question_count"],
            "total_question_count": session["target_question_count"],
            "duration_seconds": duration,
            "evidence_status": "SUFFICIENT" if sufficient else "INSUFFICIENT",
            "limitation_note": limitation,
        },
        "overall": {
            "total_score": total,
            "max_score": 100,
            "level_code": _overall_code(total),
            "level_label": _overall_label(total),
            "expectation_code": _expectation_code(total),
            "expectation_label": _expectation_label(total),
            "headline": narrative.headline,
            "summary": narrative.summary,
        },
        "score_scale": [
            {"code": "NEEDS_IMPROVEMENT", "label": "需加强", "min_inclusive": 0, "max_inclusive": 59},
            {"code": "MEETS_EXPECTATION", "label": "达到预期", "min_inclusive": 60, "max_inclusive": 84},
            {"code": "EXCELLENT", "label": "优秀", "min_inclusive": 85, "max_inclusive": 100},
        ],
        "dimensions": dimensions,
        "highlights": {
            "strengths": [
                {
                    "title": narrative.strength_title,
                    "summary": narrative.strength_summary,
                    "evidence_question_ids": [question_reviews[0]["question_id"]] if question_reviews else [],
                }
            ],
            "primary_gap": {
                "title": narrative.gap_title,
                "summary": narrative.gap_summary,
                "evidence_question_ids": [question_reviews[-1]["question_id"]] if question_reviews else [],
            },
        },
        "question_reviews": question_reviews,
        "suggestions": suggestions,
        "next_interview": {
            "position_code": "ai_agent_development",
            "position_label": "AI Agent 开发",
            "focus_code": "workflow_tool_calling",
            "focus_label": "工作流与工具调用",
            "difficulty": "senior",
            "difficulty_label": "高级",
            "reason": "继续强化工程可靠性、评测闭环和边界设计。",
        },
        "disclaimer": "本报告仅基于本场模拟问答生成，用于个人训练与复盘，不代表真实招聘评价或录用结果。",
        "assessment_metadata": {
            "rubric_version": session["rubric_version"],
            "score_scale_version": "score-scale-v1",
        },
    }


def _level_code(score: float | None) -> str:
    if score is None:
        return "INSUFFICIENT"
    if score >= 85:
        return "STRENGTH"
    if score >= 60:
        return "MEETS_EXPECTATION"
    return "NEEDS_IMPROVEMENT"


def _level_label(score: float | None) -> str:
    return {
        "INSUFFICIENT": "证据不足",
        "STRENGTH": "优势项",
        "MEETS_EXPECTATION": "达到预期",
        "NEEDS_IMPROVEMENT": "重点提升",
    }[_level_code(score)]


def _dimension_summary(code: DimensionCode, score: float | None) -> str:
    label = DIMENSION_LABELS[code][0]
    if score is None:
        return f"本场关于{label}的证据不足。"
    if score >= 85:
        return f"本场回答充分体现了{label}。"
    if score >= 60:
        return f"本场回答在{label}方面基本达到当前难度要求。"
    return f"本场回答在{label}方面存在需要优先补足的缺口。"


def _overall_code(score: float | None) -> str:
    if score is None:
        return "INSUFFICIENT"
    if score >= 85:
        return "EXCELLENT"
    if score >= 60:
        return "GOOD"
    return "NEEDS_IMPROVEMENT"


def _overall_label(score: float | None) -> str:
    return {
        "INSUFFICIENT": "暂不评分",
        "EXCELLENT": "表现优秀",
        "GOOD": "表现良好",
        "NEEDS_IMPROVEMENT": "需要加强",
    }[_overall_code(score)]


def _expectation_code(score: float | None) -> str:
    if score is None:
        return "INSUFFICIENT"
    if score >= 80:
        return "ABOVE_EXPECTATION"
    if score >= 60:
        return "MEETS_EXPECTATION"
    return "BELOW_EXPECTATION"


def _expectation_label(score: float | None) -> str:
    return {
        "INSUFFICIENT": "证据不足",
        "ABOVE_EXPECTATION": "超过本场预期",
        "MEETS_EXPECTATION": "达到本场预期",
        "BELOW_EXPECTATION": "低于本场预期",
    }[_expectation_code(score)]

