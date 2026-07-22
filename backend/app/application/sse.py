"""Contract-compliant Server-Sent Event envelope builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi.sse import ServerSentEvent

from app.core.ids import new_id
from app.core.time import utc_now_iso


@dataclass
class SseEmitter:
    session_id: str
    operation_id: str
    sequence: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)

    def make(
        self,
        event: str,
        message: str,
        payload: dict[str, Any],
        *,
        code: str = "OK",
    ) -> ServerSentEvent:
        self.sequence += 1
        event_id = new_id("evt")
        envelope = {
            "code": code,
            "message": message,
            "data": {
                "schema_version": 1,
                "event_id": event_id,
                "event": event,
                "session_id": self.session_id,
                "operation_id": self.operation_id,
                "sequence": self.sequence,
                "occurred_at": utc_now_iso(),
                "payload": payload,
            },
        }
        record = {"id": event_id, "event": event, "envelope": envelope}
        self.records.append(record)
        return self.from_record(record)

    @staticmethod
    def from_record(record: dict[str, Any]) -> ServerSentEvent:
        return ServerSentEvent(
            id=record["id"],
            event=record["event"],
            data=record["envelope"],
        )
