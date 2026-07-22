"""Async SQLite connection lifecycle and schema initialization."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id TEXT PRIMARY KEY,
    thread_id TEXT UNIQUE NOT NULL,
    graph_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'CREATED','RUNNING','WAITING_ANSWER','EVALUATING',
        'REPORTING','COMPLETED','PARTIAL','FAILED'
    )),
    position_direction TEXT NOT NULL,
    focus TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('junior','mid','senior')),
    target_question_count INTEGER NOT NULL,
    current_question_no INTEGER NOT NULL DEFAULT 0,
    completed_question_count INTEGER NOT NULL DEFAULT 0,
    current_followup_count INTEGER NOT NULL DEFAULT 0 CHECK (current_followup_count BETWEEN 0 AND 2),
    current_question_id TEXT NULL,
    pending_interrupt_id TEXT NULL,
    pending_turn_id TEXT NULL,
    blueprint_json TEXT NOT NULL DEFAULT '[]',
    rubric_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    last_error_json TEXT NULL,
    started_at TEXT NULL,
    completed_at TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question_instances (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('bank','adapted','generated')),
    bank_question_id TEXT NULL,
    variant_group TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    category_code TEXT NOT NULL,
    category_label TEXT NOT NULL,
    topic_code TEXT NOT NULL,
    topic_label TEXT NOT NULL,
    stem TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    competency_tags_json TEXT NOT NULL,
    dimension_targets_json TEXT NOT NULL,
    rubric_points_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','SCORED','ABANDONED')),
    followup_count INTEGER NOT NULL DEFAULT 0 CHECK (followup_count BETWEEN 0 AND 2),
    created_at TEXT NOT NULL,
    finalized_at TEXT NULL,
    UNIQUE(session_id, sequence_no),
    UNIQUE(session_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS interview_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    question_instance_id TEXT NOT NULL REFERENCES question_instances(id) ON DELETE CASCADE,
    turn_no INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('interviewer','candidate')),
    kind TEXT NOT NULL CHECK (kind IN ('main_question','followup','answer')),
    followup_level INTEGER NOT NULL CHECK (followup_level BETWEEN 0 AND 2),
    content TEXT NOT NULL,
    idempotency_key TEXT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(question_instance_id, turn_no)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_turn_answer_idempotency
ON interview_turns(session_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS question_evaluations (
    id TEXT PRIMARY KEY,
    question_instance_id TEXT UNIQUE NOT NULL REFERENCES question_instances(id) ON DELETE CASCADE,
    question_score REAL NOT NULL CHECK (question_score BETWEEN 0 AND 100),
    strengths_json TEXT NOT NULL,
    gaps_json TEXT NOT NULL,
    improvement TEXT NOT NULL,
    better_answer_outline_json TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_output_json TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_dimensions (
    evaluation_id TEXT NOT NULL REFERENCES question_evaluations(id) ON DELETE CASCADE,
    dimension_code TEXT NOT NULL CHECK (dimension_code IN (
        'foundation','engineering','system_design','problem_solving','communication'
    )),
    score_0_to_5 REAL NOT NULL CHECK (score_0_to_5 BETWEEN 0 AND 5),
    evidence_turn_id TEXT NOT NULL REFERENCES interview_turns(id),
    evidence_quote TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY(evaluation_id, dimension_code)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    completeness TEXT NOT NULL CHECK (completeness IN ('FULL','PARTIAL')),
    total_score REAL NULL CHECK (total_score IS NULL OR total_score BETWEEN 0 AND 100),
    report_json TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    endpoint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    session_id TEXT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','COMPLETED','FAILED')),
    result_json TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(endpoint, idempotency_key)
);
"""


class Database:
    def __init__(self, path: Path, busy_timeout_ms: int = 5000) -> None:
        self.path = path
        self.busy_timeout_ms = busy_timeout_ms
        self.connection: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        await connection.commit()
        self.connection = connection

    async def initialize(self) -> None:
        connection = self.require_connection()
        async with self.write_lock:
            await connection.executescript(SCHEMA_SQL)
            await connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, name, applied_at) "
                "VALUES(1, 'initial_schema', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
            )
            await connection.commit()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def require_connection(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("database is not connected")
        return self.connection

    async def ping(self) -> bool:
        try:
            cursor = await self.require_connection().execute("SELECT 1")
            row = await cursor.fetchone()
        except (aiosqlite.Error, RuntimeError):
            return False
        return bool(row and row[0] == 1)

