"""Question evaluation and dimension evidence persistence."""

from __future__ import annotations

from typing import Any

from app.repositories.database import Database


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def save(
        self,
        evaluation: dict[str, Any],
        dimensions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        connection = self.database.require_connection()
        columns = ", ".join(evaluation)
        placeholders = ", ".join("?" for _ in evaluation)
        async with self.database.write_lock:
            await connection.execute(
                f"INSERT OR REPLACE INTO question_evaluations ({columns}) VALUES ({placeholders})",
                tuple(evaluation.values()),
            )
            await connection.execute(
                "DELETE FROM evaluation_dimensions WHERE evaluation_id = ?",
                (evaluation["id"],),
            )
            for item in dimensions:
                item_columns = ", ".join(item)
                item_placeholders = ", ".join("?" for _ in item)
                await connection.execute(
                    f"INSERT INTO evaluation_dimensions ({item_columns}) VALUES ({item_placeholders})",
                    tuple(item.values()),
                )
            await connection.commit()
        row = await self.get_for_question(evaluation["question_instance_id"])
        if row is None:
            raise RuntimeError("evaluation was not persisted")
        return row

    async def get_for_question(self, question_id: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM question_evaluations WHERE question_instance_id = ?",
            (question_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        cursor = await self.database.require_connection().execute(
            "SELECT e.*, q.sequence_no, q.topic_code, q.topic_label, q.stem, q.followup_count "
            "FROM question_evaluations e "
            "JOIN question_instances q ON q.id = e.question_instance_id "
            "WHERE q.session_id = ? ORDER BY q.sequence_no",
            (session_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def dimensions(self, evaluation_id: str) -> list[dict[str, Any]]:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM evaluation_dimensions WHERE evaluation_id = ? ORDER BY dimension_code",
            (evaluation_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

