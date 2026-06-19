"""LangGraph 多智能体状态图编排"""
import time
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.orchestrator import (
    AgentContext,
    consult_agent,
    followup_agent,
    monitor_agent,
    planner_agent,
    router_agent,
    warning_agent,
)
from app.models import Patient
from app.services.llm_service import llm_service
from app.services.redis_client import redis_client


class GraphState(TypedDict, total=False):
    message: str
    intent: str
    reply: str
    session_id: str
    patient_id: int
    traces: list[dict]
    care_plan: dict | None
    followup: dict | None
    db: Any
    patient: Any


async def _router_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    intent = await router_agent(ctx, state["message"])
    state["intent"] = intent
    state["traces"] = ctx.traces
    return state


async def _consult_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    ctx.traces = state.get("traces", [])
    state["reply"] = await consult_agent(ctx, state["message"])
    state["traces"] = ctx.traces
    return state


async def _monitor_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    ctx.traces = state.get("traces", [])
    state["reply"] = await monitor_agent(ctx, state["message"])
    state["traces"] = ctx.traces
    return state


async def _planner_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    ctx.traces = state.get("traces", [])
    state["care_plan"] = await planner_agent(ctx, state["message"])
    state["reply"] = llm_service.DISCLAIMER + "\n\n已为您生成个性化管理方案，请查看「管理方案」页面。"
    state["traces"] = ctx.traces
    return state


async def _followup_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    ctx.traces = state.get("traces", [])
    state["followup"] = await followup_agent(ctx, state["message"])
    state["reply"] = "已为您创建随访任务，请前往「随访任务」页面完成问卷。"
    state["traces"] = ctx.traces
    return state


async def _warning_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    ctx.traces = state.get("traces", [])
    state["reply"] = await warning_agent(ctx, state["message"])
    state["traces"] = ctx.traces
    return state


async def _consult_with_plan_node(state: GraphState) -> GraphState:
    ctx = AgentContext(state["db"], state["patient"], state["session_id"])
    ctx.traces = state.get("traces", [])
    state["reply"] = await consult_agent(ctx, state["message"])
    state["traces"] = ctx.traces
    if any(k in state["message"] for k in ["头晕", "不舒服", "怎么办"]):
        ctx.traces = state["traces"]
        state["care_plan"] = await planner_agent(ctx, "根据当前症状调整管理方案")
        state["traces"] = ctx.traces
    return state


def _route_intent(state: GraphState) -> str:
    mapping = {
        "consult": "consult",
        "monitor": "monitor",
        "planner": "planner",
        "followup": "followup",
        "warning": "warning",
    }
    return mapping.get(state.get("intent", "consult"), "consult")


def build_agent_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("router", _router_node)
    workflow.add_node("consult_agent", _consult_with_plan_node)
    workflow.add_node("monitor_agent", _monitor_node)
    workflow.add_node("planner_agent", _planner_node)
    workflow.add_node("followup_agent", _followup_node)
    workflow.add_node("warning_agent", _warning_node)

    workflow.set_entry_point("router")
    workflow.add_conditional_edges("router", _route_intent, {
        "consult": "consult_agent",
        "monitor": "monitor_agent",
        "planner": "planner_agent",
        "followup": "followup_agent",
        "warning": "warning_agent",
    })
    for node in ["consult_agent", "monitor_agent", "planner_agent", "followup_agent", "warning_agent"]:
        workflow.add_edge(node, END)

    return workflow.compile()


agent_graph = build_agent_graph()


async def run_langgraph(db: AsyncSession, patient: Patient, message: str, session_id: str | None = None) -> dict[str, Any]:
    session_id = session_id or str(uuid.uuid4())
    initial: GraphState = {
        "message": message,
        "session_id": session_id,
        "patient_id": patient.id,
        "traces": [],
        "db": db,
        "patient": patient,
    }
    result = await agent_graph.ainvoke(initial)

    await redis_client.set_patient_context(patient.id, {
        "session_id": session_id,
        "last_intent": result.get("intent"),
        "diseases": patient.diseases,
    })

    return {
        "reply": result.get("reply", ""),
        "session_id": session_id,
        "agent_traces": result.get("traces", []),
        "care_plan": result.get("care_plan"),
        "followup": result.get("followup"),
        "intent": result.get("intent"),
    }
