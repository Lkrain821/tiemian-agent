"""Read models for the three frontend pages."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError, not_found
from app.core.time import parse_utc, utc_now, utc_now_iso
from app.domain.interview import (
    DIFFICULTY_LABELS,
    FOCUS_LABELS,
    STATUS_LABELS,
    Difficulty,
    FocusCode,
    InterviewStatus,
)
from app.repositories.json_utils import loads
from app.repositories.unit import Repositories
from app.services.question_bank import QuestionBank


class InterviewQueries:
    def __init__(self, repositories: Repositories, question_bank: QuestionBank, answer_max_length: int) -> None:
        self.repositories = repositories
        self.question_bank = question_bank
        self.answer_max_length = answer_max_length

    def options(self) -> dict[str, Any]:
        return {
            "product": {"code": "tiemian", "name": "铁面", "release_label": "MVP / 01"},
            "positions": [
                {
                    "code": "ai_agent_development",
                    "label": "AI Agent 开发",
                    "description": "智能体应用、RAG 与知识应用、工作流与工具调用",
                    "focus_options": [
                        {"code": code.value, "label": label, "short_label": short}
                        for code, label, short in [
                            (FocusCode.AGENT_APPLICATION_ENGINEERING, "Agent 应用工程", "应用工程"),
                            (FocusCode.RAG_KNOWLEDGE_APPLICATION, "RAG 与知识应用", "RAG 知识应用"),
                            (FocusCode.WORKFLOW_TOOL_CALLING, "工作流与工具调用", "工具与工作流"),
                        ]
                    ],
                }
            ],
            "difficulties": [
                {"code": "junior", "label": "初级", "description": "基础概念"},
                {"code": "mid", "label": "中级", "description": "工程实践"},
                {"code": "senior", "label": "高级", "description": "系统设计"},
            ],
            "defaults": {
                "position_code": "ai_agent_development",
                "focus_code": "agent_application_engineering",
                "difficulty": "mid",
            },
            "interview_spec": {
                "main_question_count": 5,
                "max_followups_per_question": 2,
                "estimated_duration_minutes": 25,
                "feedback_timing": "AFTER_INTERVIEW",
            },
            "rules": {
                "version": "mvp-1",
                "confirmation_required": True,
                "items": [
                    "本场包含 5 道主问题，每题最多追问 2 次。",
                    "面试过程中不展示分数或参考答案。",
                    "完成后生成基于本场回答证据的评估报告。",
                ],
            },
            "preview_question": {
                "topic_label": "RAG 召回诊断",
                "content": "一个 RAG 系统的召回效果突然下降，你会按照什么顺序排查？",
            },
            "usage_disclaimer": "评分仅基于本场回答，用于个人练习，不代表真实录用结果。",
        }

    async def snapshot(self, session_id: str) -> dict[str, Any]:
        session = await self.repositories.sessions.get(session_id)
        if session is None:
            raise not_found(session_id)
        questions = await self.repositories.questions.list_for_session(session_id)
        turns = await self.repositories.turns.list_for_session(session_id)
        by_number = {item["sequence_no"]: item for item in questions}
        blueprint = loads(session["blueprint_json"], [])
        current = next(
            (item for item in questions if item["id"] == session["current_question_id"]),
            None,
        )
        status = InterviewStatus(session["status"])
        started_at = parse_utc(session["started_at"])
        completed_at = parse_utc(session["completed_at"])
        end = completed_at or utc_now()
        elapsed = max(0, int((end - started_at).total_seconds())) if started_at else 0

        question_map: list[dict[str, Any]] = []
        for number in range(1, session["target_question_count"] + 1):
            item = by_number.get(number)
            planned = blueprint[number - 1] if number <= len(blueprint) else {}
            question_map.append(
                {
                    "question_id": item["id"] if item else None,
                    "number": number,
                    "topic_code": item["topic_code"] if item else planned.get("topic"),
                    "topic_label": item["topic_label"] if item else planned.get("topic_label"),
                    "status": self._question_status(item),
                    "followup_count": item["followup_count"] if item else 0,
                    "max_followups": 2,
                }
            )

        pending = None
        if status is InterviewStatus.WAITING_ANSWER and current is not None:
            pending = {
                "interrupt_id": session["pending_interrupt_id"],
                "answer_to_turn_id": session["pending_turn_id"],
                "question_id": current["id"],
                "followup_level": session["current_followup_count"],
                "min_length": 1,
                "max_length": self.answer_max_length,
                "placeholder": (
                    "组织你的思路并回答追问…"
                    if session["current_followup_count"]
                    else "组织你的思路并回答问题…"
                ),
            }

        return {
            "id": session["id"],
            "graph_version": session["graph_version"],
            "status": status.value,
            "status_label": STATUS_LABELS[status],
            "row_version": session["row_version"],
            "config": self._config(session),
            "timing": {
                "started_at": session["started_at"],
                "server_time": utc_now_iso(),
                "elapsed_seconds": elapsed,
                "completed_at": session["completed_at"],
            },
            "progress": self._progress(session, current),
            "current_question": self._current_question(current),
            "messages": [self._message(turn) for turn in turns],
            "question_map": question_map,
            "pending_answer": pending,
            "score_visibility": "AFTER_INTERVIEW",
            "available_actions": {
                "start": status is InterviewStatus.CREATED,
                "submit_answer": status is InterviewStatus.WAITING_ANSWER,
                "finish": status in {InterviewStatus.WAITING_ANSWER, InterviewStatus.FAILED},
                "retry": status is InterviewStatus.FAILED and bool(session["last_error_json"]),
                "view_report": status in {InterviewStatus.COMPLETED, InterviewStatus.PARTIAL},
            },
            "last_error": loads(session["last_error_json"], None),
        }

    async def created_interview(self, session_id: str) -> dict[str, Any]:
        snapshot = await self.snapshot(session_id)
        return {
            "id": snapshot["id"],
            "graph_version": snapshot["graph_version"],
            "status": snapshot["status"],
            "status_label": snapshot["status_label"],
            "row_version": snapshot["row_version"],
            "config": snapshot["config"],
            "spec": {
                "main_question_count": 5,
                "max_followups_per_question": 2,
                "estimated_duration_minutes": 25,
            },
            "rules_version": "mvp-1",
            "progress": snapshot["progress"],
            "created_at": (await self.repositories.sessions.get(session_id))["created_at"],
            "started_at": snapshot["timing"]["started_at"],
            "completed_at": snapshot["timing"]["completed_at"],
        }

    async def report(self, session_id: str) -> dict[str, Any]:
        session = await self.repositories.sessions.get(session_id)
        if session is None:
            raise not_found(session_id)
        stored = await self.repositories.reports.get(session_id)
        if stored is None:
            raise AppError(
                "REPORT_NOT_READY",
                "面试报告尚未生成完成",
                status_code=409,
                recoverable=True,
                details=[
                    {
                        "interview_status": session["status"],
                        "suggested_action": "GET_INTERVIEW_SNAPSHOT",
                    }
                ],
            )
        report = loads(stored["report_json"], {})
        report["id"] = stored["id"]
        return report

    async def history(self, *, page: int, page_size: int) -> dict[str, Any]:
        summary = await self.repositories.reports.history_counts()
        rows = await self.repositories.reports.list_history(
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            report = loads(row["report_json"], {})
            status = InterviewStatus(row["status"])
            completion = report.get("completion", {})
            overall = report.get("overall", {})
            items.append(
                {
                    "interview_id": row["session_id"],
                    "status": status.value,
                    "status_label": STATUS_LABELS[status],
                    "completeness": row["completeness"],
                    "generated_at": row["generated_at"],
                    "completed_at": row["completed_at"],
                    "config": report.get("config", {}),
                    "completion": {
                        "finish_reason": completion.get("finish_reason"),
                        "completed_question_count": completion.get("completed_question_count", 0),
                        "total_question_count": completion.get("total_question_count", 0),
                        "duration_seconds": completion.get("duration_seconds", 0),
                    },
                    "overall": {
                        "total_score": overall.get("total_score"),
                        "max_score": overall.get("max_score", 100),
                        "level_label": overall.get("level_label"),
                        "expectation_label": overall.get("expectation_label"),
                        "headline": overall.get("headline"),
                    },
                    "report_url": f"/api/v1/interviews/{row['session_id']}/report",
                }
            )

        total_items = summary["total_count"]
        total_pages = (total_items + page_size - 1) // page_size
        return {
            "items": items,
            "summary": summary,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
        }

    @staticmethod
    def _config(session: dict[str, Any]) -> dict[str, Any]:
        focus = FocusCode(session["focus"])
        difficulty = Difficulty(session["difficulty"])
        return {
            "position_code": "ai_agent_development",
            "position_label": "AI Agent 开发",
            "focus_code": focus.value,
            "focus_label": FOCUS_LABELS[focus],
            "difficulty": difficulty.value,
            "difficulty_label": DIFFICULTY_LABELS[difficulty],
        }

    @staticmethod
    def _progress(session: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
        total = session["target_question_count"]
        completed = session["completed_question_count"]
        return {
            "current_question_number": session["current_question_no"],
            "total_question_count": total,
            "completed_question_count": completed,
            "completion_percent": round(completed / total * 100, 2),
            "current_followup_count": session["current_followup_count"],
            "max_followups_per_question": 2,
            "current_topic_code": current["topic_code"] if current else None,
            "current_topic_label": current["topic_label"] if current else None,
        }

    @staticmethod
    def _current_question(item: dict[str, Any] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "id": item["id"],
            "number": item["sequence_no"],
            "category_code": item["category_code"],
            "category_label": item["category_label"],
            "topic_code": item["topic_code"],
            "topic_label": item["topic_label"],
            "display_title": item["topic_label"],
            "status": InterviewQueries._question_status(item),
            "followup_count": item["followup_count"],
            "max_followups": 2,
        }

    @staticmethod
    def _question_status(item: dict[str, Any] | None) -> str:
        if item is None:
            return "planned"
        return {"ACTIVE": "in_progress", "SCORED": "completed", "ABANDONED": "abandoned"}[
            item["status"]
        ]

    @staticmethod
    def _message(turn: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": turn["id"],
            "question_id": turn["question_instance_id"],
            "role": turn["role"],
            "kind": turn["kind"],
            "followup_level": turn["followup_level"],
            "content": turn["content"],
            "created_at": turn["created_at"],
        }
