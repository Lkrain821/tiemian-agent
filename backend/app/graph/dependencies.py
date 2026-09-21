"""Runtime dependencies injected into graph node closures."""

from dataclasses import dataclass

from app.core.settings import Settings
from app.decision.client import DecisionClient
from app.llm.client import InterviewLLM
from app.repositories.unit import Repositories
from app.services.question_bank import QuestionBank


@dataclass(slots=True)
class GraphDependencies:
    settings: Settings
    question_bank: QuestionBank
    llm: InterviewLLM
    repositories: Repositories
    decision: DecisionClient | None = None
