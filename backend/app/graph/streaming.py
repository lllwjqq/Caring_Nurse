"""真流式多智能体编排：对需要 LLM 生成的意图流式输出 token。"""
import time
import uuid
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.orchestrator import (
    AgentContext,
    build_consult_messages,
    build_planner_messages,
    create_care_plan,
    followup_agent,
    load_history,
    monitor_agent,
    planner_agent,
    router_agent,
    save_message,
    warning_agent,
)
from app.models import Patient
from app.services.llm_service import llm_service
from app.services.redis_client import redis_client


async def stream_agent_graph(
    db: AsyncSession, patient: Patient, message: str, session_id: str | None = None
) -> AsyncGenerator[dict[str, Any], None]:
    session_id = session_id or str(uuid.uuid4())
    history = await load_history(db, patient.id, session_id)
    ctx = AgentContext(db, patient, session_id, history=history)

    intent = await router_agent(ctx, message)
    yield {"type": "trace", "data": ctx.traces[-1]}

    await save_message(db, patient.id, session_id, "user", message)
    await db.commit()

    reply = ""
    care_plan = None
    followup = None

    if intent == "consult":
        messages = await build_consult_messages(ctx, message)
        parts: list[str] = []
        start = time.time()
        async for token in llm_service.chat_stream(messages):
            parts.append(token)
            yield {"type": "token", "data": token}
        reply = "".join(parts)
        await ctx.log_trace("consult", "symptom_consultation", {"message": message}, {"reply": reply[:300]}, start)
        yield {"type": "trace", "data": ctx.traces[-1]}
        if any(k in message for k in ["头晕", "不舒服", "怎么办"]):
            care_plan = await planner_agent(ctx, "根据当前症状调整管理方案")
            yield {"type": "trace", "data": ctx.traces[-1]}

    elif intent == "planner":
        messages = await build_planner_messages(ctx, message)
        parts = []
        start = time.time()
        async for token in llm_service.chat_stream(messages):
            parts.append(token)
            yield {"type": "token", "data": token}
        reply = "".join(parts)
        care_plan = await create_care_plan(ctx, message, reply)
        await ctx.log_trace("planner", "create_care_plan", {"message": message}, care_plan, start)
        yield {"type": "trace", "data": ctx.traces[-1]}

    elif intent == "monitor":
        reply = await monitor_agent(ctx, message)
        yield {"type": "trace", "data": ctx.traces[-1]}
        yield {"type": "token", "data": reply}

    elif intent == "followup":
        followup = await followup_agent(ctx, message)
        reply = "已为您创建随访任务，请前往「随访任务」页面完成问卷。"
        yield {"type": "trace", "data": ctx.traces[-1]}
        yield {"type": "token", "data": reply}

    elif intent == "warning":
        reply = await warning_agent(ctx, message)
        yield {"type": "trace", "data": ctx.traces[-1]}
        yield {"type": "token", "data": reply}

    else:
        messages = await build_consult_messages(ctx, message)
        parts = []
        start = time.time()
        async for token in llm_service.chat_stream(messages):
            parts.append(token)
            yield {"type": "token", "data": token}
        reply = "".join(parts)
        await ctx.log_trace("consult", "symptom_consultation", {"message": message}, {"reply": reply[:300]}, start)
        yield {"type": "trace", "data": ctx.traces[-1]}

    await save_message(db, patient.id, session_id, "assistant", reply)
    await db.commit()

    await redis_client.set_patient_context(patient.id, {
        "session_id": session_id,
        "last_intent": intent,
        "diseases": patient.diseases,
    })

    yield {
        "type": "done",
        "session_id": session_id,
        "care_plan": care_plan,
        "followup": followup,
        "intent": intent,
    }
