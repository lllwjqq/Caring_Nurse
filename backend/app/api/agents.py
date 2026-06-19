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
from app.models import AgentTrace, User
from app.schemas import AgentTraceResponse, ChatRequest, ChatResponse
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
        result = await run_agent_graph(db, patient, data.message, data.session_id)
        for trace in result["agent_traces"]:
            yield f"data: {json.dumps({'type': 'trace', 'data': trace}, ensure_ascii=False)}\n\n"
        reply = result["reply"]
        for i in range(0, len(reply), 30):
            chunk = reply[i : i + 30]
            yield f"data: {json.dumps({'type': 'token', 'data': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'session_id': result['session_id'], 'care_plan': result.get('care_plan')}, ensure_ascii=False)}\n\n"

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
