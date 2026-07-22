"""Application commands that validate, serialize, and run LangGraph."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi.sse import ServerSentEvent
from langgraph.types import Command

from app.api.schemas.interviews import (
    CreateInterviewRequest,
    FinishInterviewRequest,
    RetryInterviewRequest,
    StartInterviewRequest,
    SubmitAnswerRequest,
)
from app.application.idempotency import request_hash
from app.application.locks import SessionOperationLocks
from app.application.queries import InterviewQueries
from app.application.sse import SseEmitter
from app.core.errors import AppError, not_found
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.interview import InterviewStatus
from app.llm.prompts import PROMPT_VERSION
from app.repositories.json_utils import dumps, loads
from app.repositories.unit import Repositories


@dataclass
class PreparedStream:
    events: AsyncIterator[ServerSentEvent]


class InterviewCommands:
    def __init__(
        self,
        repositories: Repositories,
        queries: InterviewQueries,
        graph_registry: Any,
        locks: SessionOperationLocks,
        *,
        answer_max_length: int,
    ) -> None:
        self.repositories = repositories
        self.queries = queries
        self.graph_registry = graph_registry
        self.locks = locks
        self.answer_max_length = answer_max_length

    async def create_interview(
        self,
        body: CreateInterviewRequest,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[dict[str, Any], bool]:
        endpoint = "/api/v1/interviews"
        record, created = await self.repositories.idempotency.claim(
            endpoint, idempotency_key, request_hash(body), None
        )
        if not created and record["state"] == "COMPLETED" and record["result_json"]:
            return loads(record["result_json"], {}), False
        if body.rules_version != "mvp-1":
            raise AppError(
                "RULES_VERSION_EXPIRED",
                "面试规则版本已更新，请重新确认",
                status_code=409,
                recoverable=True,
            )
        if not body.rules_confirmed:
            raise AppError(
                "RULES_NOT_CONFIRMED",
                "请先确认本场面试规则",
                status_code=400,
                recoverable=True,
            )
        session_id = new_id("int")
        now = utc_now_iso()
        try:
            await self.repositories.sessions.create(
                {
                    "id": session_id,
                    "thread_id": session_id,
                    "graph_version": "interview_v1",
                    "status": InterviewStatus.CREATED.value,
                    "position_direction": body.position_code,
                    "focus": body.focus_code.value,
                    "difficulty": body.difficulty.value,
                    "target_question_count": 5,
                    "current_question_no": 0,
                    "completed_question_count": 0,
                    "current_followup_count": 0,
                    "current_question_id": None,
                    "pending_interrupt_id": None,
                    "pending_turn_id": None,
                    "blueprint_json": "[]",
                    "rubric_version": "agent-interview-rubric-v1",
                    "prompt_version": PROMPT_VERSION,
                    "row_version": 1,
                    "last_error_json": None,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            result = {
                "request_id": request_id,
                "interview": await self.queries.created_interview(session_id),
                "links": {
                    "self": f"/api/v1/interviews/{session_id}",
                    "start_stream": f"/api/v1/interviews/{session_id}/start/stream",
                },
            }
            await self.repositories.idempotency.complete(endpoint, idempotency_key, dumps(result))
            return result, True
        except Exception:
            await self.repositories.idempotency.fail(endpoint, idempotency_key)
            raise

    async def prepare_start(
        self, session_id: str, body: StartInterviewRequest, idempotency_key: str
    ) -> PreparedStream:
        session, record, created, endpoint = await self._claim(
            session_id, "start", body, idempotency_key
        )
        replay = self._replay_if_complete(record)
        if replay is not None:
            return PreparedStream(replay)
        if session["status"] != InterviewStatus.CREATED.value:
            raise AppError(
                "INTERVIEW_ALREADY_STARTED",
                "面试已经开始",
                status_code=409,
                recoverable=True,
            )
        self._check_version(session, body.expected_row_version)
        lock = await self.locks.acquire(session_id)
        return PreparedStream(
            self._run_graph(
                session=session,
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                lock=lock,
                command_name="START_INTERVIEW",
                graph_input={"session_id": session_id},
                open_payload={"command": "START_INTERVIEW", "accepted_row_version": session["row_version"]},
            )
        )

    async def prepare_answer(
        self, session_id: str, body: SubmitAnswerRequest, idempotency_key: str
    ) -> PreparedStream:
        session, record, created, endpoint = await self._claim(
            session_id, "answers", body, idempotency_key
        )
        replay = self._replay_if_complete(record)
        if replay is not None:
            return PreparedStream(replay)
        if session["status"] != InterviewStatus.WAITING_ANSWER.value:
            raise AppError(
                "INVALID_INTERVIEW_STATE",
                "当前状态不能提交回答",
                status_code=409,
                recoverable=True,
                details=[{"interview_status": session["status"]}],
            )
        self._check_version(session, body.expected_row_version)
        if (
            session["pending_interrupt_id"] != body.interrupt_id
            or session["pending_turn_id"] != body.answer_to_turn_id
        ):
            raise AppError(
                "STALE_INTERRUPT",
                "当前问题已经变化，请刷新面试状态后重新确认回答",
                status_code=409,
                recoverable=True,
                details=[
                    {
                        "submitted_interrupt_id": body.interrupt_id,
                        "current_interrupt_id": session["pending_interrupt_id"],
                        "suggested_action": "GET_INTERVIEW_SNAPSHOT",
                    }
                ],
            )
        content = body.content.strip()
        if not content:
            raise AppError(
                "ANSWER_EMPTY", "回答不能为空", status_code=422, recoverable=True
            )
        if len(content) > self.answer_max_length:
            raise AppError(
                "ANSWER_TOO_LONG",
                f"回答不能超过 {self.answer_max_length} 个字符",
                status_code=422,
                recoverable=True,
                details=[
                    {
                        "field": "content",
                        "reason": "max_length",
                        "limit": self.answer_max_length,
                        "actual": len(content),
                    }
                ],
            )
        lock = await self.locks.acquire(session_id)
        resume = {
            "type": "answer",
            "content": content,
            "answer_turn_id": new_id("turn"),
            "idempotency_key": idempotency_key,
            "created_at": utc_now_iso(),
        }
        return PreparedStream(
            self._run_graph(
                session=session,
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                lock=lock,
                command_name="SUBMIT_ANSWER",
                graph_input=Command(resume=resume),
                open_payload={"command": "SUBMIT_ANSWER", "accepted_row_version": session["row_version"]},
            )
        )

    async def prepare_finish(
        self, session_id: str, body: FinishInterviewRequest, idempotency_key: str
    ) -> PreparedStream:
        session, record, created, endpoint = await self._claim(
            session_id, "finish", body, idempotency_key
        )
        replay = self._replay_if_complete(record)
        if replay is not None:
            return PreparedStream(replay)
        if not body.confirm_partial_report:
            raise AppError(
                "PARTIAL_REPORT_NOT_CONFIRMED",
                "请确认生成部分面试报告",
                status_code=400,
                recoverable=True,
            )
        if session["status"] in {InterviewStatus.COMPLETED.value, InterviewStatus.PARTIAL.value}:
            return PreparedStream(self._terminal_replay(session, "FINISH_INTERVIEW"))
        if session["status"] != InterviewStatus.WAITING_ANSWER.value:
            raise AppError(
                "INVALID_INTERVIEW_STATE",
                "当前状态不能提前结束面试",
                status_code=409,
                recoverable=True,
            )
        self._check_version(session, body.expected_row_version)
        lock = await self.locks.acquire(session_id)
        return PreparedStream(
            self._run_graph(
                session=session,
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                lock=lock,
                command_name="FINISH_INTERVIEW",
                graph_input=Command(resume={"type": "finish"}),
                open_payload={"command": "FINISH_INTERVIEW", "accepted_row_version": session["row_version"]},
            )
        )

    async def prepare_retry(
        self, session_id: str, body: RetryInterviewRequest, idempotency_key: str
    ) -> PreparedStream:
        session, record, created, endpoint = await self._claim(
            session_id, "retry", body, idempotency_key
        )
        replay = self._replay_if_complete(record)
        if replay is not None:
            return PreparedStream(replay)
        if session["status"] != InterviewStatus.FAILED.value or not session["last_error_json"]:
            raise AppError(
                "RETRY_NOT_AVAILABLE",
                "当前没有可重试的失败步骤",
                status_code=409,
                recoverable=True,
            )
        self._check_version(session, body.expected_row_version)
        error = loads(session["last_error_json"], {})
        if error.get("failed_operation_id") != body.failed_operation_id:
            raise AppError(
                "RETRY_NOT_AVAILABLE",
                "失败操作已经变化，请刷新状态",
                status_code=409,
                recoverable=True,
            )
        lock = await self.locks.acquire(session_id)
        return PreparedStream(
            self._run_graph(
                session=session,
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                lock=lock,
                command_name="RETRY_FAILED_STEP",
                graph_input=None,
                open_payload={
                    "command": "RETRY_FAILED_STEP",
                    "accepted_row_version": session["row_version"],
                    "failed_operation_id": body.failed_operation_id,
                },
            )
        )

    async def _claim(
        self, session_id: str, action: str, body: Any, idempotency_key: str
    ) -> tuple[dict[str, Any], dict[str, Any], bool, str]:
        session = await self.repositories.sessions.get(session_id)
        if session is None:
            raise not_found(session_id)
        endpoint = f"/api/v1/interviews/{session_id}/{action}/stream"
        record, created = await self.repositories.idempotency.claim(
            endpoint, idempotency_key, request_hash(body), session_id
        )
        return session, record, created, endpoint

    @staticmethod
    def _check_version(session: dict[str, Any], expected: int) -> None:
        if session["row_version"] != expected:
            raise AppError(
                "STALE_SESSION_VERSION",
                "面试状态已经变化，请刷新后重试",
                status_code=409,
                recoverable=True,
                details=[
                    {
                        "expected_row_version": expected,
                        "current_row_version": session["row_version"],
                    }
                ],
            )

    def _replay_if_complete(self, record: dict[str, Any]) -> AsyncIterator[ServerSentEvent] | None:
        if record["state"] != "COMPLETED" or not record["result_json"]:
            return None
        records = loads(record["result_json"], {}).get("events", [])

        async def replay() -> AsyncIterator[ServerSentEvent]:
            for item in records:
                yield SseEmitter.from_record(item)

        return replay()

    async def _terminal_replay(
        self, session: dict[str, Any], command_name: str
    ) -> AsyncIterator[ServerSentEvent]:
        emitter = SseEmitter(session["id"], new_id("op"))
        yield emitter.make(
            "stream.open",
            "请求已接受",
            {"command": command_name, "accepted_row_version": session["row_version"]},
        )
        report = await self.repositories.reports.get(session["id"])
        if report:
            yield emitter.make(
                "report.completed",
                "报告已生成",
                {
                    "report_id": report["id"],
                    "completeness": report["completeness"],
                    "report_url": f"/api/v1/interviews/{session['id']}/report",
                },
            )
        yield emitter.make("interview.completed", "面试已完成", self._completion_payload(session))
        yield emitter.make("stream.done", "本次事件流已结束", self._done_payload(session))

    async def _run_graph(
        self,
        *,
        session: dict[str, Any],
        endpoint: str,
        idempotency_key: str,
        lock: asyncio.Lock,
        command_name: str,
        graph_input: Any,
        open_payload: dict[str, Any],
    ) -> AsyncIterator[ServerSentEvent]:
        operation_id = new_id("op")
        emitter = SseEmitter(session["id"], operation_id)
        try:
            yield emitter.make("stream.open", self._open_message(command_name), open_payload)
            graph = self.graph_registry.get(session["graph_version"])
            config = {"configurable": {"thread_id": session["thread_id"]}}
            async for part in graph.astream(
                graph_input,
                config,
                stream_mode="custom",
                version="v2",
            ):
                item = part.get("data", part)
                if not isinstance(item, dict) or "event" not in item:
                    continue
                event = item["event"]
                payload = dict(item.get("payload", {}))
                if event == "question.meta" and payload.get("kind") == "main_question":
                    current = payload.pop("current_question", None)
                    if current:
                        yield emitter.make(
                            "question.changed",
                            f"进入第 {current['number']} 道主问题",
                            {
                                "previous_question_id": session["current_question_id"],
                                "current_question": current,
                            },
                        )
                yield emitter.make(event, item.get("message", event), payload)

            final = await self.repositories.sessions.get(session["id"])
            if final is None:
                raise not_found(session["id"])
            if final["status"] == InterviewStatus.WAITING_ANSWER.value:
                snapshot = await self.queries.snapshot(session["id"])
                yield emitter.make(
                    "waiting.answer",
                    "等待用户回答追问"
                    if snapshot["progress"]["current_followup_count"]
                    else "等待用户回答",
                    {
                        "row_version": final["row_version"],
                        "pending_answer": snapshot["pending_answer"],
                    },
                )
            yield emitter.make("stream.done", "本次事件流已结束", self._done_payload(final))
            await self.repositories.idempotency.complete(
                endpoint, idempotency_key, dumps({"events": emitter.records})
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = exc if isinstance(exc, AppError) else AppError(
                "INTERNAL_ERROR",
                "当前步骤执行失败",
                status_code=500,
                recoverable=True,
            )
            failed_at = utc_now_iso()
            last_error = {
                "code": error.code,
                "message": error.message,
                "recoverable": error.recoverable,
                "failed_step": command_name.lower(),
                "failed_operation_id": operation_id,
                "retry_endpoint": f"/api/v1/interviews/{session['id']}/retry/stream",
                "occurred_at": failed_at,
            }
            try:
                failed = await self.repositories.sessions.update(
                    session["id"],
                    {
                        "status": InterviewStatus.FAILED.value,
                        "last_error_json": dumps(last_error),
                        "updated_at": failed_at,
                    },
                )
                yield emitter.make(
                    "error",
                    error.message,
                    {
                        "error_code": error.code,
                        "recoverable": error.recoverable,
                        "failed_step": last_error["failed_step"],
                        "failed_operation_id": operation_id,
                        "retry_endpoint": last_error["retry_endpoint"],
                        "snapshot_url": f"/api/v1/interviews/{session['id']}",
                    },
                    code=error.code,
                )
                yield emitter.make(
                    "stream.done",
                    "本次事件流因可恢复错误结束",
                    self._done_payload(failed, reason="RECOVERABLE_ERROR"),
                )
                await self.repositories.idempotency.fail(
                    endpoint, idempotency_key, dumps({"events": emitter.records})
                )
            except asyncio.CancelledError:
                raise
        finally:
            if lock.locked():
                lock.release()

    @staticmethod
    def _open_message(command: str) -> str:
        return {
            "START_INTERVIEW": "开始面试请求已接受",
            "SUBMIT_ANSWER": "提交回答请求已接受",
            "FINISH_INTERVIEW": "提前结束请求已接受",
            "RETRY_FAILED_STEP": "重试请求已接受",
        }[command]

    @staticmethod
    def _completion_payload(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": session["status"],
            "finish_reason": (
                "ALL_QUESTIONS_COMPLETED"
                if session["status"] == InterviewStatus.COMPLETED.value
                else "USER_REQUESTED"
            ),
            "completed_question_count": session["completed_question_count"],
            "total_question_count": session["target_question_count"],
            "completed_at": session["completed_at"],
        }

    @staticmethod
    def _done_payload(session: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        final_status = session["status"]
        if reason is None:
            reason = {
                InterviewStatus.WAITING_ANSWER.value: "WAITING_ANSWER",
                InterviewStatus.COMPLETED.value: "FULL_REPORT_READY",
                InterviewStatus.PARTIAL.value: "PARTIAL_REPORT_READY",
                InterviewStatus.FAILED.value: "RECOVERABLE_ERROR",
            }.get(final_status, final_status)
        return {
            "reason": reason,
            "final_status": final_status,
            "row_version": session["row_version"],
            "snapshot_url": f"/api/v1/interviews/{session['id']}",
            "report_url": (
                f"/api/v1/interviews/{session['id']}/report"
                if final_status in {InterviewStatus.COMPLETED.value, InterviewStatus.PARTIAL.value}
                else None
            ),
        }
