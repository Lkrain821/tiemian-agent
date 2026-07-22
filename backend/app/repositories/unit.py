"""Repository facade injected into application and graph services."""

from app.repositories.database import Database
from app.repositories.evaluations import EvaluationRepository
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.questions import QuestionRepository
from app.repositories.reports import ReportRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository


class Repositories:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.sessions = SessionRepository(database)
        self.questions = QuestionRepository(database)
        self.turns = TurnRepository(database)
        self.evaluations = EvaluationRepository(database)
        self.reports = ReportRepository(database)
        self.idempotency = IdempotencyRepository(database)

