"""LangGraph 图定义（仅用于展示 / 答辩）。

运行时唯一入口是 app.graph.orchestrator.handle_message / handle_stream。
本文件不再被 API 调用；按规格 §15，不把 db / patient 放进 state。
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.graph.orchestrator import (
    consult_agent,
    diagnosis_agent,
    document_agent,
    medication_agent,
    monitor_agent,
    planner_agent,
    router_agent,
    safety_agent,
)

# 仅用于可视化的 agent 注册表（真正的执行在 orchestrator）
AGENT_REGISTRY = {
    "safety": safety_agent,
    "router": router_agent,
    "consult": consult_agent,
    "monitor": monitor_agent,
    "planner": planner_agent,
    "document": document_agent,
    "medication": medication_agent,
    "diagnosis": diagnosis_agent,
}


class GraphState(TypedDict, total=False):
    message: str
    intent: str


def _pass(state: GraphState) -> GraphState:
    return state


def _route(state: GraphState) -> str:
    return state.get("intent", "consult")


def build_agent_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("safety", _pass)
    workflow.add_node("router", _pass)
    for name in ("consult", "monitor", "planner", "document", "medication", "diagnosis"):
        workflow.add_node(name, _pass)

    workflow.set_entry_point("safety")
    workflow.add_edge("safety", "router")
    workflow.add_conditional_edges(
        "router",
        _route,
        {
            "consult": "consult",
            "monitor": "monitor",
            "planner": "planner",
            "document": "document",
            "medication": "medication",
            "diagnosis": "diagnosis",
        },
    )
    for name in ("consult", "monitor", "planner", "document", "medication", "diagnosis"):
        workflow.add_edge(name, END)
    return workflow.compile()


agent_graph = build_agent_graph()
