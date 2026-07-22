"""Interview lifecycle enums and immutable product constants."""

from enum import StrEnum


class InterviewStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_ANSWER = "WAITING_ANSWER"
    EVALUATING = "EVALUATING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class Difficulty(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class FocusCode(StrEnum):
    AGENT_APPLICATION_ENGINEERING = "agent_application_engineering"
    RAG_KNOWLEDGE_APPLICATION = "rag_knowledge_application"
    WORKFLOW_TOOL_CALLING = "workflow_tool_calling"


STATUS_LABELS = {
    InterviewStatus.CREATED: "等待开始",
    InterviewStatus.RUNNING: "面试进行中",
    InterviewStatus.WAITING_ANSWER: "等待回答",
    InterviewStatus.EVALUATING: "正在评估",
    InterviewStatus.REPORTING: "正在生成报告",
    InterviewStatus.COMPLETED: "已完成",
    InterviewStatus.PARTIAL: "已提前结束",
    InterviewStatus.FAILED: "当前步骤失败",
}


FOCUS_LABELS = {
    FocusCode.AGENT_APPLICATION_ENGINEERING: "Agent 应用工程",
    FocusCode.RAG_KNOWLEDGE_APPLICATION: "RAG 与知识应用",
    FocusCode.WORKFLOW_TOOL_CALLING: "工作流与工具调用",
}


DIFFICULTY_LABELS = {
    Difficulty.JUNIOR: "初级",
    Difficulty.MID: "中级",
    Difficulty.SENIOR: "高级",
}

