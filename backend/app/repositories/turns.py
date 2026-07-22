"""Interview turn persistence and evidence queries."""

from __future__ import annotations

from typing import Any

from app.repositories.database import Database


class TurnRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, values: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        connection = self.database.require_connection()
        async with self.database.write_lock:
            cursor = await connection.execute(
                f"INSERT OR IGNORE INTO interview_turns ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            created = cursor.rowcount == 1
            await connection.commit()
        row = await self.get(values["id"])
        if row is None and values.get("idempotency_key"):
            row = await self.get_by_idempotency(values["session_id"], values["idempotency_key"])
        if row is None:
            raise RuntimeError("turn was not persisted")
        return row, created

    async def get(self, turn_id: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM interview_turns WHERE id = ?", (turn_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_by_idempotency(self, session_id: str, key: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM interview_turns WHERE session_id = ? AND idempotency_key = ?",
            (session_id, key),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_for_question(self, question_id: str) -> list[dict[str, Any]]:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM interview_turns WHERE question_instance_id = ? ORDER BY turn_no",
            (question_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM interview_turns WHERE session_id = ? "
            "ORDER BY created_at, question_instance_id, turn_no",
            (session_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

