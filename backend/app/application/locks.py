"""In-process guard that prevents concurrent graph runs for one session."""

import asyncio

from app.core.errors import AppError


class SessionOperationLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._map_lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> asyncio.Lock:
        async with self._map_lock:
            lock = self._locks.setdefault(session_id, asyncio.Lock())
            if lock.locked():
                raise AppError(
                    "ACTIVE_OPERATION_EXISTS",
                    "当前面试已有正在执行的操作",
                    status_code=409,
                    recoverable=True,
                    details=[{"interview_id": session_id}],
                )
            await lock.acquire()
            return lock

