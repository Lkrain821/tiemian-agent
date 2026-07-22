from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from tests.fakes import FakeInterviewLLM


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-pro",
        app_db_path=tmp_path / "business.sqlite3",
        checkpoint_db_path=tmp_path / "checkpoints.sqlite3",
        question_bank_path=REPOSITORY_ROOT / "data" / "questions.json",
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings=settings, llm=FakeInterviewLLM())
    with TestClient(app) as test_client:
        yield test_client
