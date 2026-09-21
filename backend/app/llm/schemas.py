"""Validated structured outputs produced by the DeepSeek adapter."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.rubric import DimensionCode


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuestionAdaptation(StrictModel):
    stem: str = Field(min_length=10, max_length=1200)


class AnswerAssessment(StrictModel):
    answer_relevance: Literal["relevant", "partially_relevant", "off_topic"]
    followup_needed: bool
    followup_focus: str | None = Field(default=None, max_length=300)
    rationale: str = Field(min_length=1, max_length=800)

    @model_validator(mode="after")
    def validate_focus(self) -> "AnswerAssessment":
        if self.followup_needed and not self.followup_focus:
            raise ValueError("followup_focus is required when followup_needed is true")
        return self


class FollowupGeneration(StrictModel):
    question: str = Field(min_length=5, max_length=600)


class EvidenceItem(StrictModel):
    dimension_code: DimensionCode
    turn_id: str
    quote: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)


class QuestionEvaluation(StrictModel):
    dimension_scores: dict[DimensionCode, float]
    evidence: list[EvidenceItem]
    strengths: list[str] = Field(min_length=0, max_length=4)
    gaps: list[str] = Field(min_length=0, max_length=4)
    improvement: str = Field(min_length=0, max_length=800)
    better_answer_outline: list[str] = Field(min_length=0, max_length=5)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_scores(self) -> "QuestionEvaluation":
        for score in self.dimension_scores.values():
            if not 0 <= score <= 5:
                raise ValueError("dimension scores must be between 0 and 5")
        return self


class SuggestionDraft(StrictModel):
    title: str
    why: str
    actions: list[str] = Field(min_length=1, max_length=4)
    completion_criteria: str


class ReportNarrative(StrictModel):
    headline: str
    summary: str
    strength_title: str
    strength_summary: str
    gap_title: str
    gap_summary: str
    suggestions: list[SuggestionDraft] = Field(min_length=3, max_length=3)

