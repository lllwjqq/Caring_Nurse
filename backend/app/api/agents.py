import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.database import get_db
from app.graph.langgraph_app import run_langgraph as run_agent_graph
from app.graph.streaming import stream_agent_graph
from app.models import AgentTrace, ChatMessage, User
from app.schemas import (
    AgentTraceResponse,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionSummary,
)
from app.services.llm_service import llm_service
from app.services.rag_service import RAGService

router = APIRouter(prefix="/agents", tags=["多智能体"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    result = await run_agent_graph(db, patient, data.message, data.session_id)
    return ChatResponse(
        reply=result["reply"],
        session_id=result["session_id"],
        agent_traces=result["agent_traces"],
        care_plan=result.get("care_plan"),
    )


@router.post("/chat/stream")
async def chat_stream(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)

    async def event_generator():
        async for event in stream_agent_graph(db, patient, data.message, data.session_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/traces/{session_id}", response_model=list[AgentTraceResponse])
async def get_traces(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(AgentTrace)
        .where(AgentTrace.session_id == session_id, AgentTrace.patient_id == patient.id)
        .order_by(AgentTrace.created_at)
    )
    return result.scalars().all()


@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前患者的全部历史会话（短时记忆），按最近活跃倒序。"""
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient.id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()

    grouped: dict[str, dict] = {}
    for m in messages:
        s = grouped.setdefault(
            m.session_id,
            {"session_id": m.session_id, "title": "", "message_count": 0, "last_message_at": m.created_at},
        )
        s["message_count"] += 1
        s["last_message_at"] = m.created_at
        if not s["title"] and m.role == "user":
            s["title"] = (m.content or "").strip()[:30] or "新对话"

    summaries = sorted(grouped.values(), key=lambda x: x["last_message_at"], reverse=True)
    return [ChatSessionSummary(**s) for s in summaries]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """恢复某个会话的完整消息历史（按时间正序）。"""
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient.id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()
