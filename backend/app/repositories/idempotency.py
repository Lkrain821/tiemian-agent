"""Persistent idempotency records for command endpoints."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.core.time import utc_now_iso
from app.repositories.database import Database


class IdempotencyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def claim(
        self,
        endpoint: str,
        key: str,
        request_hash: str,
        session_id: str | None,
    ) -> tuple[dict[str, Any], bool]:
        now = utc_now_iso()
        connection = self.database.require_connection()
        async with self.database.write_lock:
            cursor = await connection.execute(
                "INSERT OR IGNORE INTO idempotency_records "
                "(endpoint, idempotency_key, request_hash, session_id, state, result_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'PENDING', NULL, ?, ?)",
                (endpoint, key, request_hash, session_id, now, now),
            )
            created = cursor.rowcount == 1
            await connection.commit()
        record = await self.get(endpoint, key)
        if record is None:
            raise RuntimeError("idempotency record was not persisted")
        if record["request_hash"] != request_hash:
            raise AppError(
                "IDEMPOTENCY_CONFLICT",
                "同一幂等键不能用于不同请求",
                status_code=409,
                details=[{"endpoint": endpoint}],
            )
        return record, created

    async def complete(self, endpoint: str, key: str, result_json: str) -> None:
        connection = self.database.require_connection()
        async with self.database.write_lock:
            await connection.execute(
                "UPDATE idempotency_records SET state = 'COMPLETED', result_json = ?, updated_at = ? "
                "WHERE endpoint = ? AND idempotency_key = ?",
                (result_json, utc_now_iso(), endpoint, key),
            )
            await connection.commit()

    async def fail(self, endpoint: str, key: str, result_json: str | None = None) -> None:
        connection = self.database.require_connection()
        async with self.database.write_lock:
            await connection.execute(
                "UPDATE idempotency_records SET state = 'FAILED', result_json = ?, updated_at = ? "
                "WHERE endpoint = ? AND idempotency_key = ?",
                (result_json, utc_now_iso(), endpoint, key),
            )
            await connection.commit()

    async def get(self, endpoint: str, key: str) -> dict[str, Any] | None:
        cursor = await self.database.require_connection().execute(
            "SELECT * FROM idempotency_records WHERE endpoint = ? AND idempotency_key = ?",
            (endpoint, key),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

