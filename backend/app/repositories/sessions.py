"""Interview session repository with optimistic concurrency."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.repositories.database import Database


SESSION_UPDATE_FIELDS = {
    "status",
    "current_question_no",
    "completed_question_count",
    "current_followup_count",
    "current_question_id",
    "pending_interrupt_id",
    "pending_turn_id",
    "blueprint_json",
    "last_error_json",
    "started_at",
    "completed_at",
    "updated_at",
}


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, values: dict[str, Any]) -> dict[str, Any]:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        connection = self.database.require_connection()
        async with self.database.write_lock:
            await connection.execute(
                f"INSERT INTO interview_sessions ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            await connection.commit()
        return await self.get(values["id"])

    async def get(self, session_id: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM interview_sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update(
        self,
        session_id: str,
        values: dict[str, Any],
        *,
        expected_row_version: int | None = None,
    ) -> dict[str, Any]:
        invalid = set(values) - SESSION_UPDATE_FIELDS
        if invalid:
            raise ValueError(f"unsupported session fields: {sorted(invalid)}")
        if not values:
            current = await self.get(session_id)
            if current is None:
                raise KeyError(session_id)
            return current

        assignments = ", ".join(f"{name} = ?" for name in values)
        parameters: list[Any] = [*values.values(), session_id]
        where = "id = ?"
        if expected_row_version is not None:
            where += " AND row_version = ?"
            parameters.append(expected_row_version)
        connection = self.database.require_connection()
        async with self.database.write_lock:
            cursor = await connection.execute(
                f"UPDATE interview_sessions SET {assignments}, row_version = row_version + 1 "
                f"WHERE {where}",
                tuple(parameters),
            )
            if cursor.rowcount != 1:
                await connection.rollback()
                exists = await self.get(session_id)
                if exists is None:
                    raise KeyError(session_id)
                raise AppError(
                    "STALE_SESSION_VERSION",
                    "面试状态已经变化，请刷新后重试",
                    status_code=409,
                    recoverable=True,
                    details=[
                        {
                            "expected_row_version": expected_row_version,
                            "current_row_version": exists["row_version"],
                        }
                    ],
                )
            await connection.commit()
        updated = await self.get(session_id)
        if updated is None:
            raise KeyError(session_id)
        return updated

