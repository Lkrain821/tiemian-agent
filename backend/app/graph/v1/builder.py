"""Build and compile the immutable interview_v1 graph."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.dependencies import GraphDependencies
from app.graph.v1.nodes.interview import InterviewNodes
from app.graph.v1.routing import (
    route_assessment,
    route_fallback_assessment,
    route_input,
    route_next_question,
    route_validation,
)
from app.graph.v1.state import InterviewState


def build_interview_graph(dependencies: GraphDependencies, checkpointer: Any) -> Any:
    nodes = InterviewNodes(dependencies)
    graph = StateGraph(InterviewState)

    graph.add_node("initialize_session", nodes.initialize_session)
    graph.add_node("build_blueprint", nodes.build_blueprint)
    graph.add_node("select_question", nodes.select_question)
    graph.add_node("compose_question", nodes.compose_question)
    graph.add_node("persist_prompt", nodes.persist_prompt)
    graph.add_node("await_answer", nodes.await_answer)
    graph.add_node("validate_answer", nodes.validate_answer)
    graph.add_node("prepare_validation_prompt", nodes.prepare_validation_prompt)
    graph.add_node("persist_answer", nodes.persist_answer)
    graph.add_node("assess_answer", nodes.assess_answer)
    graph.add_node("fallback_assessment", nodes.fallback_assessment)
    graph.add_node("compose_followup", nodes.compose_followup)
    graph.add_node("score_question", nodes.score_question)
    graph.add_node("persist_question_result", nodes.persist_question_result)
    graph.add_node("advance_question", nodes.advance_question)
    graph.add_node("mark_partial", nodes.mark_partial)
    graph.add_node("generate_report", nodes.generate_report)
    graph.add_node("persist_report", nodes.persist_report)

    graph.add_edge(START, "initialize_session")
    graph.add_edge("initialize_session", "build_blueprint")
    graph.add_edge("build_blueprint", "select_question")
    graph.add_edge("select_question", "compose_question")
    graph.add_edge("compose_question", "persist_prompt")
    graph.add_edge("persist_prompt", "await_answer")
    graph.add_conditional_edges(
        "await_answer", route_input, {"finish": "mark_partial", "answer": "validate_answer"}
    )
    graph.add_conditional_edges(
        "validate_answer",
        route_validation,
        {"valid": "persist_answer", "invalid": "prepare_validation_prompt"},
    )
    graph.add_edge("prepare_validation_prompt", "await_answer")
    graph.add_edge("persist_answer", "assess_answer")
    graph.add_conditional_edges(
        "assess_answer",
        lambda state: route_assessment(state, dependencies.settings),
        {"followup": "compose_followup", "score": "score_question", "fallback": "fallback_assessment"},
    )
    graph.add_conditional_edges(
        "fallback_assessment", route_fallback_assessment,
        {"followup": "compose_followup", "score": "score_question"},
    )
    graph.add_edge("compose_followup", "persist_prompt")
    graph.add_edge("score_question", "persist_question_result")
    graph.add_edge("persist_question_result", "advance_question")
    graph.add_conditional_edges(
        "advance_question",
        route_next_question,
        {"next": "select_question", "report": "generate_report"},
    )
    graph.add_edge("mark_partial", "generate_report")
    graph.add_edge("generate_report", "persist_report")
    graph.add_edge("persist_report", END)

    return graph.compile(checkpointer=checkpointer)
