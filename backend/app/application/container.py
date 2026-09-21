"""Explicit dependency container built once during application lifespan."""

from dataclasses import dataclass
from typing import Any

from app.application.commands import InterviewCommands
from app.application.queries import InterviewQueries
from app.core.settings import Settings
from app.repositories.database import Database
from app.repositories.unit import Repositories
from app.services.question_bank import QuestionBank


@dataclass
class ApplicationContainer:
    settings: Settings
    database: Database
    repositories: Repositories
    question_bank: QuestionBank
    llm: Any
    graph_registry: Any
    queries: InterviewQueries
    commands: InterviewCommands
    decision: Any = None
