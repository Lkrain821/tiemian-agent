"""Question instance persistence."""

from __future__ import annotations

from typing import Any

from app.repositories.database import Database


class QuestionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, values: dict[str, Any]) -> dict[str, Any]:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        connection = self.database.require_connection()
        async with self.database.write_lock:
            await connection.execute(
                f"INSERT OR IGNORE INTO question_instances ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            await connection.commit()
        row = await self.get(values["id"])
        if row is None:
            raise RuntimeError("question instance was not persisted")
        return row

    async def get(self, question_id: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM question_instances WHERE id = ?", (question_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM question_instances WHERE session_id = ? ORDER BY sequence_no",
            (session_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def update(self, question_id: str, values: dict[str, Any]) -> dict[str, Any]:
        allowed = {"status", "stem", "source", "fingerprint", "followup_count", "finalized_at"}
        invalid = set(values) - allowed
        if invalid:
            raise ValueError(f"unsupported question fields: {sorted(invalid)}")
        connection = self.database.require_connection()
        assignments = ", ".join(f"{key} = ?" for key in values)
        async with self.database.write_lock:
            cursor = await connection.execute(
                f"UPDATE question_instances SET {assignments} WHERE id = ?",
                (*values.values(), question_id),
            )
            if cursor.rowcount != 1:
                await connection.rollback()
                raise KeyError(question_id)
            await connection.commit()
        row = await self.get(question_id)
        if row is None:
            raise KeyError(question_id)
        return row

