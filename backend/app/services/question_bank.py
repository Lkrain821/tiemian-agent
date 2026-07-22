"""Versioned question bank loading, validation, and deterministic selection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import AppError
from app.domain.interview import Difficulty, FocusCode
from app.domain.rubric import DimensionCode


TopicCode = Literal[
    "rag",
    "function_calling",
    "langgraph",
    "multi_agent",
    "context_engineering",
    "agent_evaluation",
]


class RubricPoints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_points: list[str] = Field(min_length=2)
    common_errors: list[str] = Field(min_length=1)


class QuestionSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    variant_group: str
    direction: Literal["ai_agent_development"]
    focus_tags: list[FocusCode] = Field(min_length=1)
    topic: TopicCode
    topic_label: str
    difficulty: Difficulty
    competency_tags: list[str] = Field(min_length=1)
    dimension_targets: dict[DimensionCode, float]
    stem: str = Field(min_length=10)
    followup_axes: list[str] = Field(min_length=1)
    rubric_points: RubricPoints
    version: int = Field(ge=1)
    enabled: bool

    @model_validator(mode="after")
    def validate_dimension_targets(self) -> "QuestionSeed":
        total = sum(self.dimension_targets.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError("dimension_targets must sum to 1")
        return self


class QuestionBankDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    direction: Literal["ai_agent_development"]
    questions: list[QuestionSeed]


BLUEPRINT_TOPICS: dict[FocusCode, list[TopicCode]] = {
    FocusCode.AGENT_APPLICATION_ENGINEERING: [
        "context_engineering",
        "function_calling",
        "langgraph",
        "multi_agent",
        "agent_evaluation",
    ],
    FocusCode.RAG_KNOWLEDGE_APPLICATION: [
        "rag",
        "context_engineering",
        "agent_evaluation",
        "function_calling",
        "langgraph",
    ],
    FocusCode.WORKFLOW_TOOL_CALLING: [
        "function_calling",
        "langgraph",
        "multi_agent",
        "agent_evaluation",
        "context_engineering",
    ],
}


class QuestionBank:
    def __init__(self, document: QuestionBankDocument) -> None:
        self.version = document.version
        self.questions = [question for question in document.questions if question.enabled]
        self._validate_unique()

    @classmethod
    def load(cls, path: Path) -> "QuestionBank":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            document = QuestionBankDocument.model_validate(raw)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AppError(
                "SERVICE_NOT_READY",
                "题库加载失败",
                status_code=503,
                recoverable=True,
                details=[{"component": "question_bank", "reason": type(exc).__name__}],
            ) from exc
        return cls(document)

    def blueprint(self, focus: FocusCode, count: int = 5) -> list[dict[str, str]]:
        return [
            {"slot": str(index + 1), "topic": topic, "topic_label": self.topic_label(topic)}
            for index, topic in enumerate(BLUEPRINT_TOPICS[focus][:count])
        ]

    def select(
        self,
        *,
        session_id: str,
        slot: int,
        topic: TopicCode,
        difficulty: Difficulty,
        used_question_ids: set[str],
        used_variant_groups: set[str],
    ) -> QuestionSeed:
        candidates = [
            question
            for question in self.questions
            if question.topic == topic
            and question.difficulty == difficulty
            and question.id not in used_question_ids
            and question.variant_group not in used_variant_groups
        ]
        if not candidates:
            candidates = [
                question
                for question in self.questions
                if question.topic == topic
                and question.id not in used_question_ids
                and question.variant_group not in used_variant_groups
            ]
        if not candidates:
            raise AppError(
                "QUESTION_GENERATION_FAILED",
                "题库没有可用候选题",
                status_code=503,
                recoverable=True,
                details=[{"topic": topic, "slot": slot}],
            )
        return min(
            candidates,
            key=lambda question: hashlib.sha256(
                f"{session_id}:{slot}:{question.id}".encode()
            ).hexdigest(),
        )

    def counts(self) -> dict[str, dict[str, int] | int]:
        by_topic: dict[str, int] = {}
        by_difficulty: dict[str, int] = {}
        for question in self.questions:
            by_topic[question.topic] = by_topic.get(question.topic, 0) + 1
            by_difficulty[question.difficulty.value] = by_difficulty.get(question.difficulty.value, 0) + 1
        return {"total": len(self.questions), "by_topic": by_topic, "by_difficulty": by_difficulty}

    @staticmethod
    def fingerprint(stem: str) -> str:
        normalized = re.sub(r"\s+", "", stem).lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _validate_unique(self) -> None:
        ids = [question.id for question in self.questions]
        variants = [question.variant_group for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question IDs must be unique")
        if len(variants) != len(set(variants)):
            raise ValueError("variant groups must be unique in seed version 1")

    def topic_label(self, topic: TopicCode) -> str:
        for question in self.questions:
            if question.topic == topic:
                return question.topic_label
        return topic

