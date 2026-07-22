"""Deterministic LLM double; test scenarios never call the paid provider."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.llm.schemas import (
    AnswerAssessment,
    QuestionEvaluation,
    ReportNarrative,
)
from app.core.errors import LLMServiceError


class FakeInterviewLLM:
    model_name = "fake-deepseek-v4-pro"

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        return "测试响应"

    async def stream(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> AsyncIterator[str]:
        user = messages[-1]["content"]
        if "种子题：" in user:
            text = user.split("种子题：", 1)[1].split("\n考察点：", 1)[0]
        else:
            text = "请继续说明你会采用哪些可观测指标和失败回退策略？"
        midpoint = max(1, len(text) // 2)
        yield text[:midpoint]
        yield text[midpoint:]

    async def complete_json(
        self,
        messages: Sequence[dict[str, str]],
        schema: type[Any],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> Any:
        if schema is AnswerAssessment:
            turns = _turns(messages[-1]["content"])
            answers = [item for item in turns if item["role"] == "candidate"]
            latest = answers[-1]["content"]
            if "[OFFTOPIC]" in latest:
                needed = True
                relevance = "off_topic"
            elif "[BAD]" in latest:
                needed = len(answers) == 1
                relevance = "partially_relevant"
            else:
                needed = False
                relevance = "relevant"
            return AnswerAssessment(
                answer_relevance=relevance,
                followup_needed=needed,
                followup_focus="补充可验证指标与失败回退" if needed else None,
                rationale="测试评分路径",
            )
        if schema is QuestionEvaluation:
            content = messages[-1]["content"]
            turns = _turns(content)
            answers = [item for item in turns if item["role"] == "candidate"]
            evidence_turn = answers[-1]
            if any("[OFFTOPIC]" in item["content"] for item in answers):
                score = 0.5
            elif any("[BAD]" in item["content"] for item in answers):
                score = 2.2
            else:
                score = 4.5
            target_match = re.search(r"目标维度：(\{.*?\})\n评分要点：", content, re.S)
            assert target_match
            targets = json.loads(target_match.group(1))
            quote = evidence_turn["content"][:400]
            return QuestionEvaluation.model_validate(
                {
                    "dimension_scores": {code: score for code in targets},
                    "evidence": [
                        {
                            "dimension_code": code,
                            "turn_id": evidence_turn["turn_id"],
                            "quote": quote,
                            "reason": "该回答直接体现目标维度",
                        }
                        for code in targets
                    ],
                    "strengths": ["回答包含可验证的技术判断"],
                    "gaps": ["仍可补充边界条件和量化阈值"],
                    "improvement": "按结论、证据、取舍和回退路径组织回答。",
                    "better_answer_outline": [
                        "先明确问题边界",
                        "再给出分层方案与验证指标",
                        "最后说明失败条件和回退动作",
                    ],
                    "confidence": 0.95,
                }
            )
        if schema is ReportNarrative:
            return ReportNarrative.model_validate(
                {
                    "headline": "本场回答已形成可回溯的 Agent 能力画像。",
                    "summary": "报告只采用本场回答证据，并按统一评分标准汇总。",
                    "strength_title": "能够结构化分析 Agent 工程问题",
                    "strength_summary": "回答能覆盖实现、验证和风险控制。",
                    "gap_title": "量化门槛仍可更明确",
                    "gap_summary": "部分回答还可以补充基线、阈值和回退触发条件。",
                    "suggestions": [
                        {
                            "title": "完善评测闭环",
                            "why": "让技术判断可以被验证。",
                            "actions": ["建立版本化回归集", "定义发布和回退阈值"],
                            "completion_criteria": "能给出一套指标到动作的发布门禁。",
                        },
                        {
                            "title": "加强工程复盘",
                            "why": "用真实故障补足边界意识。",
                            "actions": ["复盘一次工具调用故障"],
                            "completion_criteria": "明确根因、指标和预防措施。",
                        },
                        {
                            "title": "优化技术表达",
                            "why": "提高面试答案的信息密度。",
                            "actions": ["练习结论先行的三段式回答"],
                            "completion_criteria": "三分钟内讲清方案、取舍与回退。",
                        },
                    ],
                }
            )
        raise AssertionError(f"unexpected schema: {schema}")

    async def healthcheck(self) -> bool:
        return True


class FailOnceAssessmentLLM(FakeInterviewLLM):
    def __init__(self) -> None:
        self.failed = False

    async def complete_json(
        self,
        messages: Sequence[dict[str, str]],
        schema: type[Any],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> Any:
        if schema is AnswerAssessment and not self.failed:
            self.failed = True
            raise LLMServiceError(
                "ASSESSMENT_FAILED",
                "测试：评分暂时失败",
                status_code=503,
                recoverable=True,
            )
        return await super().complete_json(
            messages,
            schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _turns(content: str) -> list[dict[str, Any]]:
    match = re.search(r"问答链：(\[.*\])$", content, re.S)
    assert match
    return json.loads(match.group(1))
