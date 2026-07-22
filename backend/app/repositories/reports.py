"""Final and partial report persistence."""

from __future__ import annotations

from typing import Any

from app.repositories.database import Database


class ReportRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def save(self, values: dict[str, Any]) -> dict[str, Any]:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        updates = ", ".join(f"{name}=excluded.{name}" for name in values if name not in {"id", "session_id"})
        connection = self.database.require_connection()
        async with self.database.write_lock:
            await connection.execute(
                f"INSERT INTO reports ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT(session_id) DO UPDATE SET {updates}",
                tuple(values.values()),
            )
            await connection.commit()
        row = await self.get(values["session_id"])
        if row is None:
            raise RuntimeError("report was not persisted")
        return row

    async def get(self, session_id: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM reports WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_history(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        cursor = await self.database.require_connection().execute(
            "SELECT r.session_id, r.completeness, r.report_json, r.generated_at, "
            "s.status, s.completed_at "
            "FROM reports AS r "
            "JOIN interview_sessions AS s ON s.id = r.session_id "
            "WHERE s.status IN ('COMPLETED', 'PARTIAL') "
            "ORDER BY COALESCE(s.completed_at, r.generated_at) DESC, "
            "r.generated_at DESC, s.id DESC "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def history_counts(self) -> dict[str, int]:
        cursor = await self.database.require_connection().execute(
            "SELECT COUNT(*) AS total_count, "
            "COALESCE(SUM(CASE WHEN r.completeness = 'FULL' THEN 1 ELSE 0 END), 0) "
            "AS full_count, "
            "COALESCE(SUM(CASE WHEN r.completeness = 'PARTIAL' THEN 1 ELSE 0 END), 0) "
            "AS partial_count "
            "FROM reports AS r "
            "JOIN interview_sessions AS s ON s.id = r.session_id "
            "WHERE s.status IN ('COMPLETED', 'PARTIAL')"
        )
        row = await cursor.fetchone()
        if row is None:
            return {"total_count": 0, "full_count": 0, "partial_count": 0}
        return {name: int(row[name]) for name in ("total_count", "full_count", "partial_count")}
