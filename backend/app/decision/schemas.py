"""Internal decision contracts and validated TypeSafe wire primitives."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Probability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerDecision(DecisionModel):
    answer_relevance: Literal["relevant", "partially_relevant", "off_topic"]
    followup_probability: Probability
    # Conservative minimum of the relevance and target Choice confidences.
    # Noul has no confidence field; this is not Noul confidence.
    followup_confidence: Probability
    followup_target: str | None
    decision_source: Literal["jev"] = "jev"


class DecisionMetadata(DecisionModel):
    provider: Literal["jev", "deepseek", "deepseek_fallback", "limit"]
    latency_ms: float = Field(ge=0)
    fallback_reason: str | None = None
    confidence_source: str | None = None


class ChoiceAnswer(DecisionModel):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, Probability]
    confidence: Probability

    @model_validator(mode="after")
    def validate_distribution(self) -> "ChoiceAnswer":
        if self.choice not in self.probabilities:
            raise ValueError("choice missing from probability distribution")
        if abs(sum(self.probabilities.values()) - 1) > 0.001:
            raise ValueError("probabilities must sum to one")
        if self.probabilities[self.choice] < max(self.probabilities.values()):
            raise ValueError("choice must have maximum probability")
        return self


class NoulAnswer(DecisionModel):
    type: Literal["noul"]
    noul: Probability
