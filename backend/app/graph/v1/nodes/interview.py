"""Node implementations for the versioned interview state machine."""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from app.core.errors import AppError, LLMServiceError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.interview import Difficulty, FocusCode, InterviewStatus
from app.domain.rubric import DimensionCode
from app.graph.dependencies import GraphDependencies
from app.graph.v1.state import InterviewState
from app.llm.prompts import (
    PROMPT_VERSION,
    assessment_messages,
    evaluation_messages,
    followup_messages,
    question_adaptation_messages,
    report_messages,
)
from app.llm.schemas import AnswerAssessment, QuestionEvaluation, ReportNarrative
from app.repositories.json_utils import dumps
from app.services.reporting import build_report, report_context
from app.services.scoring import validate_evaluation


class InterviewNodes:
    def __init__(self, dependencies: GraphDependencies) -> None:
        self.deps = dependencies

    async def initialize_session(self, state: InterviewState) -> dict[str, Any]:
        session = await self._session(state["session_id"])
        now = utc_now_iso()
        values: dict[str, Any] = {
            "status": InterviewStatus.RUNNING.value,
            "updated_at": now,
        }
        if session["started_at"] is None:
            values["started_at"] = now
        updated = await self.deps.repositories.sessions.update(session["id"], values)
        return {
            "graph_version": "interview_v1",
            "position_direction": session["position_direction"],
            "focus": session["focus"],
            "difficulty": session["difficulty"],
            "target_question_count": session["target_question_count"],
            "max_followups": self.deps.settings.max_followups_per_question,
            "question_blueprint": [],
            "used_question_ids": [],
            "used_variant_groups": [],
            "used_fingerprints": [],
            "current_question_no": 0,
            "completed_question_count": 0,
            "current_followup_count": 0,
            "current_turns": [],
            "question_results": [],
            "finish_requested": False,
            "finish_reason": None,
            "status": updated["status"],
            "failure": None,
        }

    async def build_blueprint(self, state: InterviewState) -> dict[str, Any]:
        blueprint = self.deps.question_bank.blueprint(
            FocusCode(state["focus"]), state["target_question_count"]
        )
        await self.deps.repositories.sessions.update(
            state["session_id"],
            {"blueprint_json": dumps(blueprint), "updated_at": utc_now_iso()},
        )
        return {"question_blueprint": blueprint}

    async def select_question(self, state: InterviewState) -> dict[str, Any]:
        sequence_no = state.get("current_question_no", 0) + 1
        slot = state["question_blueprint"][sequence_no - 1]
        seed = self.deps.question_bank.select(
            session_id=state["session_id"],
            slot=sequence_no,
            topic=slot["topic"],  # type: ignore[arg-type]
            difficulty=Difficulty(state["difficulty"]),
            used_question_ids=set(state.get("used_question_ids", [])),
            used_variant_groups=set(state.get("used_variant_groups", [])),
        )
        selected = seed.model_dump(mode="json")
        selected.update(
            {
                "instance_id": new_id("qinst"),
                "sequence_no": sequence_no,
                "category_code": seed.focus_tags[0].value,
                "category_label": seed.topic_label,
            }
        )
        return {"selected_question": selected}

    async def compose_question(self, state: InterviewState) -> dict[str, Any]:
        seed = state["selected_question"]
        if seed is None:
            raise RuntimeError("selected_question is required")
        writer = get_stream_writer()
        message_id = new_id("turn")
        question_id = seed["instance_id"]
        writer(
            {
                "event": "question.meta",
                "message": "主问题元数据已生成",
                "payload": {
                    "message_id": message_id,
                    "question_id": question_id,
                    "kind": "main_question",
                    "followup_level": 0,
                    "current_question": {
                        "id": question_id,
                        "number": seed["sequence_no"],
                        "category_code": seed["category_code"],
                        "category_label": seed["category_label"],
                        "topic_code": seed["topic"],
                        "topic_label": seed["topic_label"],
                        "display_title": seed["topic_label"],
                        "status": "in_progress",
                        "followup_count": 0,
                        "max_followups": state["max_followups"],
                    },
                },
            }
        )
        parts: list[str] = []
        source = "adapted"
        try:
            async for chunk in self.deps.llm.stream(
                question_adaptation_messages(seed, state["difficulty"]), max_tokens=700
            ):
                parts.append(chunk)
                writer(
                    {
                        "event": "question.delta",
                        "message": "问题文本分片",
                        "payload": {
                            "message_id": message_id,
                            "chunk_index": len(parts) - 1,
                            "text": chunk,
                        },
                    }
                )
        except LLMServiceError:
            parts = [seed["stem"]]
            source = "bank"
            writer(
                {
                    "event": "question.delta",
                    "message": "题库问题文本",
                    "payload": {"message_id": message_id, "chunk_index": 0, "text": seed["stem"]},
                }
            )
        stem = "".join(parts).strip() or seed["stem"]
        fingerprint = self.deps.question_bank.fingerprint(stem)
        if fingerprint in state.get("used_fingerprints", []):
            stem = seed["stem"]
            fingerprint = self.deps.question_bank.fingerprint(stem)
            source = "bank"
        question = {
            "id": question_id,
            "number": seed["sequence_no"],
            "source": source,
            "bank_question_id": seed["id"],
            "variant_group": seed["variant_group"],
            "fingerprint": fingerprint,
            "category_code": seed["category_code"],
            "category_label": seed["category_label"],
            "topic_code": seed["topic"],
            "topic_label": seed["topic_label"],
            "display_title": seed["topic_label"],
            "stem": stem,
            "difficulty": seed["difficulty"],
            "competency_tags": seed["competency_tags"],
            "dimension_targets": seed["dimension_targets"],
            "rubric_points": seed["rubric_points"],
            "status": "in_progress",
            "followup_count": 0,
            "max_followups": state["max_followups"],
        }
        pending = {
            "interrupt_id": new_id("intr"),
            "id": message_id,
            "question_id": question_id,
            "role": "interviewer",
            "kind": "main_question",
            "followup_level": 0,
            "content": stem,
            "created_at": utc_now_iso(),
        }
        return {
            "current_question": question,
            "current_question_no": seed["sequence_no"],
            "current_followup_count": 0,
            "current_turns": [],
            "pending_prompt": pending,
        }

    async def persist_prompt(self, state: InterviewState) -> dict[str, Any]:
        question = state["current_question"]
        prompt = state["pending_prompt"]
        if question is None or prompt is None:
            raise RuntimeError("current question and prompt are required")
        if prompt["kind"] == "main_question":
            await self.deps.repositories.questions.create(
                {
                    "id": question["id"],
                    "session_id": state["session_id"],
                    "sequence_no": question["number"],
                    "source": question["source"],
                    "bank_question_id": question["bank_question_id"],
                    "variant_group": question["variant_group"],
                    "fingerprint": question["fingerprint"],
                    "category_code": question["category_code"],
                    "category_label": question["category_label"],
                    "topic_code": question["topic_code"],
                    "topic_label": question["topic_label"],
                    "stem": question["stem"],
                    "difficulty": question["difficulty"],
                    "competency_tags_json": dumps(question["competency_tags"]),
                    "dimension_targets_json": dumps(question["dimension_targets"]),
                    "rubric_points_json": dumps(question["rubric_points"]),
                    "status": "ACTIVE",
                    "followup_count": 0,
                    "created_at": prompt["created_at"],
                    "finalized_at": None,
                }
            )
        else:
            await self.deps.repositories.questions.update(
                question["id"], {"followup_count": prompt["followup_level"]}
            )
        turn_values = {
            "id": prompt["id"],
            "session_id": state["session_id"],
            "question_instance_id": question["id"],
            "turn_no": len(state.get("current_turns", [])) + 1,
            "role": "interviewer",
            "kind": prompt["kind"],
            "followup_level": prompt["followup_level"],
            "content": prompt["content"],
            "idempotency_key": None,
            "created_at": prompt["created_at"],
        }
        persisted, _ = await self.deps.repositories.turns.create(turn_values)
        session = await self.deps.repositories.sessions.update(
            state["session_id"],
            {
                "status": InterviewStatus.WAITING_ANSWER.value,
                "current_question_no": question["number"],
                "current_followup_count": prompt["followup_level"],
                "current_question_id": question["id"],
                "pending_interrupt_id": prompt["interrupt_id"],
                "pending_turn_id": prompt["id"],
                "last_error_json": None,
                "updated_at": utc_now_iso(),
            },
        )
        writer = get_stream_writer()
        writer(
            {
                "event": "question.completed",
                "message": "问题已生成",
                "payload": {"message": self._message_payload(persisted)},
            }
        )
        writer(
            {
                "event": "progress.updated",
                "message": "面试进度已更新",
                "payload": {"row_version": session["row_version"], "progress": self._progress(session, question)},
            }
        )
        used_ids = list(state.get("used_question_ids", []))
        used_variants = list(state.get("used_variant_groups", []))
        used_fingerprints = list(state.get("used_fingerprints", []))
        if prompt["kind"] == "main_question":
            used_ids.append(question["bank_question_id"])
            used_variants.append(question["variant_group"])
            used_fingerprints.append(question["fingerprint"])
        return {
            "current_turns": [*state.get("current_turns", []), persisted],
            "used_question_ids": used_ids,
            "used_variant_groups": used_variants,
            "used_fingerprints": used_fingerprints,
            "status": session["status"],
        }

    async def await_answer(self, state: InterviewState) -> dict[str, Any]:
        prompt = state["pending_prompt"]
        if prompt is None:
            raise RuntimeError("pending prompt is required")
        resumed = interrupt(
            {
                "interrupt_id": prompt["interrupt_id"],
                "answer_to_turn_id": prompt["id"],
                "question_id": prompt["question_id"],
                "followup_level": prompt["followup_level"],
                "min_length": 1,
                "max_length": self.deps.settings.answer_max_length,
                "placeholder": (
                    "组织你的思路并回答追问…"
                    if prompt["followup_level"]
                    else "组织你的思路并回答问题…"
                ),
            }
        )
        return {"pending_input": resumed}

    async def validate_answer(self, state: InterviewState) -> dict[str, Any]:
        pending = dict(state.get("pending_input") or {})
        content = str(pending.get("content", "")).strip()
        if not content:
            return {
                "input_valid": False,
                "validation_error": {"code": "ANSWER_EMPTY", "message": "回答不能为空"},
            }
        if len(content) > self.deps.settings.answer_max_length:
            return {
                "input_valid": False,
                "validation_error": {"code": "ANSWER_TOO_LONG", "message": "回答超过长度限制"},
            }
        pending["content"] = content
        return {"pending_input": pending, "input_valid": True, "validation_error": None}

    async def prepare_validation_prompt(self, state: InterviewState) -> dict[str, Any]:
        return {"pending_input": None, "status": InterviewStatus.WAITING_ANSWER.value}

    async def persist_answer(self, state: InterviewState) -> dict[str, Any]:
        pending = state["pending_input"]
        question = state["current_question"]
        if pending is None or question is None:
            raise RuntimeError("answer and question are required")
        turn_values = {
            "id": pending["answer_turn_id"],
            "session_id": state["session_id"],
            "question_instance_id": question["id"],
            "turn_no": len(state.get("current_turns", [])) + 1,
            "role": "candidate",
            "kind": "answer",
            "followup_level": state["current_followup_count"],
            "content": pending["content"],
            "idempotency_key": pending["idempotency_key"],
            "created_at": pending["created_at"],
        }
        persisted, _ = await self.deps.repositories.turns.create(turn_values)
        session = await self.deps.repositories.sessions.update(
            state["session_id"],
            {
                "status": InterviewStatus.EVALUATING.value,
                "pending_interrupt_id": None,
                "pending_turn_id": None,
                "updated_at": utc_now_iso(),
            },
        )
        get_stream_writer()(
            {
                "event": "answer.accepted",
                "message": "回答已保存",
                "payload": {
                    "answer_turn_id": persisted["id"],
                    "question_id": question["id"],
                    "followup_level": persisted["followup_level"],
                    "created_at": persisted["created_at"],
                    "row_version": session["row_version"],
                },
            }
        )
        turns = state.get("current_turns", [])
        if not any(turn["id"] == persisted["id"] for turn in turns):
            turns = [*turns, persisted]
        return {"current_turns": turns, "status": session["status"]}

    async def assess_answer(self, state: InterviewState) -> dict[str, Any]:
        question = state["current_question"]
        if question is None:
            raise RuntimeError("current question is required")
        try:
            assessment = await self.deps.llm.complete_json(
                assessment_messages(
                    question, state["current_turns"], state["current_followup_count"]
                ),
                AnswerAssessment,
                max_tokens=900,
            )
        except LLMServiceError as exc:
            raise _stage_llm_error(exc, "ASSESSMENT_FAILED", "回答评估失败") from exc
        return {"answer_assessment": assessment.model_dump(mode="json")}

    async def compose_followup(self, state: InterviewState) -> dict[str, Any]:
        question = state["current_question"]
        assessment = state["answer_assessment"]
        if question is None or assessment is None:
            raise RuntimeError("question and assessment are required")
        level = state["current_followup_count"] + 1
        message_id = new_id("turn")
        writer = get_stream_writer()
        writer(
            {
                "event": "question.meta",
                "message": "追问元数据已生成",
                "payload": {
                    "message_id": message_id,
                    "question_id": question["id"],
                    "kind": "followup",
                    "followup_level": level,
                },
            }
        )
        parts: list[str] = []
        async for chunk in self.deps.llm.stream(
            followup_messages(
                question,
                state["current_turns"],
                str(assessment["followup_focus"]),
            ),
            max_tokens=500,
        ):
            parts.append(chunk)
            writer(
                {
                    "event": "question.delta",
                    "message": "问题文本分片",
                    "payload": {
                        "message_id": message_id,
                        "chunk_index": len(parts) - 1,
                        "text": chunk,
                    },
                }
            )
        text = "".join(parts).strip()
        if not text:
            raise AppError(
                "QUESTION_GENERATION_FAILED",
                "追问生成失败",
                status_code=503,
                recoverable=True,
            )
        pending = {
            "interrupt_id": new_id("intr"),
            "id": message_id,
            "question_id": question["id"],
            "role": "interviewer",
            "kind": "followup",
            "followup_level": level,
            "content": text,
            "created_at": utc_now_iso(),
        }
        question = {**question, "followup_count": level}
        return {
            "current_question": question,
            "current_followup_count": level,
            "pending_prompt": pending,
        }

    async def score_question(self, state: InterviewState) -> dict[str, Any]:
        question = state["current_question"]
        if question is None:
            raise RuntimeError("current question is required")
        try:
            evaluation = await self.deps.llm.complete_json(
                evaluation_messages(question, state["current_turns"]),
                QuestionEvaluation,
                max_tokens=2400,
            )
        except LLMServiceError as exc:
            raise _stage_llm_error(exc, "ASSESSMENT_FAILED", "题目评分失败") from exc
        question_score, evidence = validate_evaluation(
            evaluation, question, state["current_turns"]
        )
        output = evaluation.model_dump(mode="json")
        output["question_score"] = question_score
        output["evidence"] = [item.model_dump(mode="json") for item in evidence]
        return {"question_evaluation": output}

    async def persist_question_result(self, state: InterviewState) -> dict[str, Any]:
        question = state["current_question"]
        output = state["question_evaluation"]
        if question is None or output is None:
            raise RuntimeError("question evaluation is required")
        evaluation_id = new_id("eval")
        dimensions = []
        for evidence in output["evidence"]:
            code = DimensionCode(evidence["dimension_code"])
            dimensions.append(
                {
                    "evaluation_id": evaluation_id,
                    "dimension_code": code.value,
                    "score_0_to_5": output["dimension_scores"][code.value],
                    "evidence_turn_id": evidence["turn_id"],
                    "evidence_quote": evidence["quote"],
                    "reason": evidence["reason"],
                }
            )
        created_at = utc_now_iso()
        stored = await self.deps.repositories.evaluations.save(
            {
                "id": evaluation_id,
                "question_instance_id": question["id"],
                "question_score": output["question_score"],
                "strengths_json": dumps(output["strengths"]),
                "gaps_json": dumps(output["gaps"]),
                "improvement": output["improvement"],
                "better_answer_outline_json": dumps(output["better_answer_outline"]),
                "rubric_version": "agent-interview-rubric-v1",
                "prompt_version": PROMPT_VERSION,
                "model_name": self.deps.llm.model_name,
                "model_output_json": dumps(output),
                "confidence": output["confidence"],
                "created_at": created_at,
            },
            dimensions,
        )
        await self.deps.repositories.questions.update(
            question["id"], {"status": "SCORED", "finalized_at": created_at}
        )
        completed = state["completed_question_count"] + 1
        session = await self.deps.repositories.sessions.update(
            state["session_id"],
            {
                "completed_question_count": completed,
                "updated_at": created_at,
            },
        )
        result = {
            "evaluation_id": stored["id"],
            "question_id": question["id"],
            "question_number": question["number"],
        }
        return {
            "completed_question_count": completed,
            "question_results": [*state.get("question_results", []), result],
            "status": session["status"],
        }

    async def advance_question(self, state: InterviewState) -> dict[str, Any]:
        session = await self.deps.repositories.sessions.update(
            state["session_id"],
            {
                "status": InterviewStatus.RUNNING.value,
                "current_followup_count": 0,
                "current_question_id": None,
                "pending_interrupt_id": None,
                "pending_turn_id": None,
                "updated_at": utc_now_iso(),
            },
        )
        return {
            "selected_question": None,
            "current_question": None,
            "current_followup_count": 0,
            "current_turns": [],
            "pending_prompt": None,
            "pending_input": None,
            "answer_assessment": None,
            "question_evaluation": None,
            "status": session["status"],
        }

    async def mark_partial(self, state: InterviewState) -> dict[str, Any]:
        question = state.get("current_question")
        if question is not None:
            await self.deps.repositories.questions.update(
                question["id"], {"status": "ABANDONED", "finalized_at": utc_now_iso()}
            )
        session = await self.deps.repositories.sessions.update(
            state["session_id"],
            {
                "status": InterviewStatus.REPORTING.value,
                "pending_interrupt_id": None,
                "pending_turn_id": None,
                "updated_at": utc_now_iso(),
            },
        )
        return {
            "finish_requested": True,
            "finish_reason": "USER_REQUESTED",
            "status": session["status"],
        }

    async def generate_report(self, state: InterviewState) -> dict[str, Any]:
        session = await self._session(state["session_id"])
        if session["status"] != InterviewStatus.REPORTING.value:
            session = await self.deps.repositories.sessions.update(
                state["session_id"],
                {"status": InterviewStatus.REPORTING.value, "updated_at": utc_now_iso()},
            )
        evaluations = await self.deps.repositories.evaluations.list_for_session(state["session_id"])
        dimension_rows = {
            item["id"]: await self.deps.repositories.evaluations.dimensions(item["id"])
            for item in evaluations
        }
        try:
            narrative = await self.deps.llm.complete_json(
                report_messages(report_context(session, evaluations)),
                ReportNarrative,
                max_tokens=2200,
            )
        except LLMServiceError as exc:
            raise _stage_llm_error(
                exc, "REPORT_GENERATION_FAILED", "面试报告生成失败"
            ) from exc
        session["finish_reason"] = state.get("finish_reason")
        report = await build_report(
            session=session,
            evaluations=evaluations,
            dimension_rows=dimension_rows,
            narrative=narrative,
            partial_score_min_questions=self.deps.settings.partial_score_min_questions,
        )
        report["id"] = new_id("rpt")
        writer = get_stream_writer()
        for index, chunk in enumerate(_chunks(narrative.summary, 28)):
            writer(
                {
                    "event": "report.delta",
                    "message": "报告文本分片",
                    "payload": {"section": "summary", "chunk_index": index, "text": chunk},
                }
            )
        return {"report": report, "status": InterviewStatus.REPORTING.value}

    async def persist_report(self, state: InterviewState) -> dict[str, Any]:
        report = state["report"]
        if report is None:
            raise RuntimeError("report is required")
        now = utc_now_iso()
        await self.deps.repositories.reports.save(
            {
                "id": report["id"],
                "session_id": state["session_id"],
                "completeness": report["completeness"],
                "total_score": report["overall"]["total_score"],
                "report_json": dumps(report),
                "rubric_version": "agent-interview-rubric-v1",
                "prompt_version": PROMPT_VERSION,
                "model_name": self.deps.llm.model_name,
                "generated_at": report["generated_at"],
                "updated_at": now,
            }
        )
        final_status = (
            InterviewStatus.COMPLETED
            if report["completeness"] == "FULL"
            else InterviewStatus.PARTIAL
        )
        session = await self.deps.repositories.sessions.update(
            state["session_id"],
            {
                "status": final_status.value,
                "current_question_id": None,
                "pending_interrupt_id": None,
                "pending_turn_id": None,
                "completed_at": now,
                "updated_at": now,
            },
        )
        writer = get_stream_writer()
        report_url = f"/api/v1/interviews/{state['session_id']}/report"
        writer(
            {
                "event": "report.completed",
                "message": "报告已生成",
                "payload": {
                    "report_id": report["id"],
                    "completeness": report["completeness"],
                    "report_url": report_url,
                },
            }
        )
        writer(
            {
                "event": "interview.completed",
                "message": "面试已完成" if final_status == InterviewStatus.COMPLETED else "面试已提前结束",
                "payload": {
                    "status": final_status.value,
                    "finish_reason": report["completion"]["finish_reason"],
                    "completed_question_count": session["completed_question_count"],
                    "total_question_count": session["target_question_count"],
                    "completed_at": now,
                },
            }
        )
        return {"status": final_status.value, "report": report}

    async def _session(self, session_id: str) -> dict[str, Any]:
        session = await self.deps.repositories.sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    @staticmethod
    def _message_payload(turn: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": turn["id"],
            "question_id": turn["question_instance_id"],
            "role": turn["role"],
            "kind": turn["kind"],
            "followup_level": turn["followup_level"],
            "content": turn["content"],
            "created_at": turn["created_at"],
        }

    @staticmethod
    def _progress(session: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
        total = session["target_question_count"]
        completed = session["completed_question_count"]
        return {
            "current_question_number": session["current_question_no"],
            "total_question_count": total,
            "completed_question_count": completed,
            "completion_percent": round(completed / total * 100, 2),
            "current_followup_count": session["current_followup_count"],
            "max_followups_per_question": 2,
            "current_topic_code": question["topic_code"],
            "current_topic_label": question["topic_label"],
        }


def _chunks(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


def _stage_llm_error(exc: LLMServiceError, code: str, message: str) -> LLMServiceError:
    if exc.code in {"LLM_TIMEOUT", "LLM_RATE_LIMITED"}:
        return exc
    return LLMServiceError(
        code,
        message,
        status_code=503,
        recoverable=True,
        details=exc.details,
    )
