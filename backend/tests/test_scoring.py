# Unit tests for evidence validation and score calculation.

import pytest

from app.core.errors import AppError
from app.llm.schemas import QuestionEvaluation
from app.services.scoring import validate_evaluation

QUESTION = {"dimension_targets": {"foundation": 0.5, "engineering": 0.5}}

TURNS = [
    {"id": "turn_i1", "role": "interviewer", "kind": "main_question", "content": "主问题"},
    {"id": "turn_a1", "role": "candidate", "kind": "answer", "content": "不知道"},
    {"id": "turn_i2", "role": "interviewer", "kind": "followup", "content": "追问"},
    {"id": "turn_a2", "role": "candidate", "kind": "answer", "content": "都不知道"},
]


def _item(dimension: str, turn_id: str, quote: str) -> dict:
    return {"dimension_code": dimension, "turn_id": turn_id, "quote": quote, "reason": "证据说明"}


def _evaluation(evidence, scores=None):
    return QuestionEvaluation.model_validate(
        {
            "dimension_scores": scores or {"foundation": 1.0, "engineering": 1.0},
            "evidence": evidence,
            "strengths": ["优点"],
            "gaps": ["不足"],
            "improvement": "建议",
            "better_answer_outline": ["要点"],
            "confidence": 0.9,
        }
    )


def test_exact_quotes_pass():
    evaluation = _evaluation(
        [_item("foundation", "turn_a1", "不知道"), _item("engineering", "turn_a2", "都不知道")]
    )
    score, evidence = validate_evaluation(evaluation, QUESTION, TURNS)
    assert score == 20.0
    assert [item.quote for item in evidence] == ["不知道", "都不知道"]


def test_quote_with_trailing_punctuation_is_corrected():
    evaluation = _evaluation(
        [_item("foundation", "turn_a1", "不知道。"), _item("engineering", "turn_a2", "都不知道…")]
    )
    score, evidence = validate_evaluation(evaluation, QUESTION, TURNS)
    assert score == 20.0
    assert [item.quote for item in evidence] == ["不知道", "都不知道"]


def test_wrong_turn_id_is_rebound_to_matching_answer():
    evaluation = _evaluation(
        [_item("foundation", "turn_i2", "不知道"), _item("engineering", "turn_a2", "都不知道")]
    )
    score, evidence = validate_evaluation(evaluation, QUESTION, TURNS)
    assert score == 20.0
    assert [item.turn_id for item in evidence] == ["turn_a1", "turn_a2"]


def test_unmappable_quote_falls_back_to_latest_answer():
    evaluation = _evaluation(
        [_item("foundation", "turn_a1", "我不知道如何选择工具"), _item("engineering", "turn_a2", "都没有思路")]
    )
    score, evidence = validate_evaluation(evaluation, QUESTION, TURNS)
    assert score == 20.0
    assert all(item.turn_id == "turn_a2" for item in evidence)
    assert [item.quote for item in evidence] == ["都不知道", "都不知道"]


def test_missing_dimension_score_raises():
    evaluation = _evaluation([_item("foundation", "turn_a1", "不知道")], scores={"foundation": 1.0})
    with pytest.raises(AppError) as exc:
        validate_evaluation(evaluation, QUESTION, TURNS)
    assert exc.value.code == "ASSESSMENT_FAILED"
    assert "目标维度" in exc.value.message


def test_no_candidate_answer_raises():
    evaluation = _evaluation([_item("foundation", "turn_a1", "不知道")])
    with pytest.raises(AppError) as exc:
        validate_evaluation(evaluation, QUESTION, TURNS[:1])
    assert exc.value.code == "ASSESSMENT_FAILED"
    assert "无法映射" in exc.value.message


def test_missing_dimension_evidence_is_synthesized_from_latest_answer():
    # The model returned evidence for only one of the two target dimensions.
    evaluation = _evaluation([_item("foundation", "turn_a1", "不知道")])
    score, evidence = validate_evaluation(evaluation, QUESTION, TURNS)
    assert score == 20.0
    assert sorted(item.dimension_code.value for item in evidence) == ["engineering", "foundation"]
    engineering = next(item for item in evidence if item.dimension_code.value == "engineering")
    assert engineering.turn_id == "turn_a2"
    assert engineering.quote == "都不知道"
    assert "兜底" in engineering.reason


def test_empty_evidence_is_synthesized_for_all_dimensions():
    evaluation = _evaluation([])
    score, evidence = validate_evaluation(evaluation, QUESTION, TURNS)
    assert score == 20.0
    assert len(evidence) == 2
    assert all(item.turn_id == "turn_a2" for item in evidence)
    assert all(item.quote == "都不知道" for item in evidence)


def test_schema_allows_empty_text_lists():
    evaluation = QuestionEvaluation.model_validate(
        {
            "dimension_scores": {"foundation": 0.0, "engineering": 0.0},
            "evidence": [],
            "strengths": [],
            "gaps": [],
            "improvement": "",
            "better_answer_outline": [],
            "confidence": 0.9,
        }
    )
    assert evaluation.strengths == []
