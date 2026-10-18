import time
import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AgentTrace, CarePlan, ChatMessage, FollowUp, Patient
from app.services.document_parser import summarize_medical_record
from app.services.health_service import HealthService
from app.services.llm_service import llm_service
from app.services.rag_service import RAGService
from app.services.redis_client import redis_client

HISTORY_LIMIT = 10
SESSION_LIMIT = 20  # 每患者最多保留的历史会话数，新建第 21 个时自动删除最旧会话


DOCUMENT_MARKERS = (
    "主诉", "现病史", "既往史", "家族史", "体格检查", "辅助检查",
    "诊断依据", "治疗方案", "出院医嘱", "入院诊断", "出院诊断",
    "入院日期", "出院日期", "治疗经过", "实验室检查", "影像学检查",
)


def looks_like_medical_record(message: str) -> bool:
    """聊天粘贴病历识别：文本足够长且命中至少 2 个病历结构标记词。

    长度门槛避免把「胸痛、呼吸困难」这类短急症描述误判为病历。
    """
    if len(message) < 80:
        return False
    return sum(1 for marker in DOCUMENT_MARKERS if marker in message) >= 2


async def load_history(db: AsyncSession, patient_id: int, session_id: str, limit: int = HISTORY_LIMIT) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient_id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def save_message(db: AsyncSession, patient_id: int, session_id: str, role: str, content: str):
    db.add(ChatMessage(patient_id=patient_id, session_id=session_id, role=role, content=content))
    await db.flush()


async def delete_session_records(db: AsyncSession, patient_id: int, session_id: str) -> None:
    """删除某个会话的消息与 trace（会话上限淘汰与用户手动删除共用）。"""
    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.patient_id == patient_id, ChatMessage.session_id == session_id
        )
    )
    await db.execute(
        delete(AgentTrace).where(
            AgentTrace.patient_id == patient_id, AgentTrace.session_id == session_id
        )
    )


async def enforce_session_limit(db: AsyncSession, patient_id: int, limit: int = SESSION_LIMIT) -> None:
    """超过上限时，按最近活跃时间删除最旧的会话，仅保留最新 limit 个。"""
    result = await db.execute(
        select(ChatMessage.session_id, func.max(ChatMessage.created_at).label("last_ts"))
        .where(ChatMessage.patient_id == patient_id)
        .group_by(ChatMessage.session_id)
        .order_by(func.max(ChatMessage.created_at).desc())
    )
    sessions = list(result.all())
    if len(sessions) <= limit:
        return
    for session_id, _last_ts in sessions[limit:]:
        await delete_session_records(db, patient_id, session_id)


class AgentContext:
    def __init__(self, db: AsyncSession, patient: Patient, session_id: str, history: list[dict] | None = None):
        self.db = db
        self.patient = patient
        self.session_id = session_id
        self.traces: list[dict] = []
        self.history = history or []

    async def log_trace(self, agent_name: str, action: str, input_data: dict, output_data: dict, start: float):
        duration = int((time.time() - start) * 1000)
        trace = AgentTrace(
            patient_id=self.patient.id,
            session_id=self.session_id,
            agent_name=agent_name,
            action=action,
            input_data=input_data,
            output_data=output_data,
            duration_ms=duration,
        )
        self.db.add(trace)
        await self.db.flush()
        self.traces.append({
            "agent": agent_name,
            "action": action,
            "duration_ms": duration,
            "output_summary": str(output_data)[:200],
        })


async def document_agent(ctx: AgentContext, message: str) -> tuple[str, str]:
    """病历粘贴：分类 → 结构化抽取 → 口语化摘要。返回 (回复, llm_mode)。"""
    start = time.time()
    result = await summarize_medical_record(message)
    if not result:
        await ctx.log_trace("document", "medical_record_summary",
                            {"message": message[:200]}, {"failed": True}, start)
        return "抱歉，我暂时无法识别这份病历内容，请稍后重试或直接描述您的问题。", "rule"
    summary_text = result["summary_text"]
    llm_mode = "llm" if result["summary"].get("summary_text") else "rule"
    await ctx.log_trace("document", "medical_record_summary",
                        {"message": message[:200]},
                        {"doc_type": result["doc_type"], "llm_mode": llm_mode}, start)
    return "已为您整理病历摘要：\n" + summary_text, llm_mode


async def router_agent(ctx: AgentContext, message: str) -> str:
    start = time.time()
    msg = message.lower()
    if any(k in msg for k in ["录入", "记录", "上传", "数据"]):
        intent = "monitor"
    elif any(k in msg for k in ["方案", "计划", "饮食", "运动", "建议"]):
        intent = "planner"
    elif any(k in msg for k in ["随访", "复查", "依从"]):
        intent = "followup"
    elif any(k in msg for k in ["预警", "异常", "危险"]):
        intent = "warning"
    else:
        intent = "consult"
    await ctx.log_trace("router", "intent_classification", {"message": message}, {"intent": intent}, start)
    return intent


async def build_consult_messages(ctx: AgentContext, message: str) -> list[dict]:
    context = ""
    if settings.enable_rag:
        rag = RAGService(ctx.db)
        disease = ctx.patient.diseases[0] if ctx.patient.diseases else None
        chunks = await rag.search(message, disease=disease)
        context = rag.format_context(chunks)

    health_svc = HealthService(ctx.db)
    recent = await health_svc.get_recent_records(ctx.patient.id, 5)
    records_text = "\n".join(
        f"- {r.record_type.value}: {r.value}{r.unit} ({r.recorded_at.strftime('%Y-%m-%d')})"
        for r in recent
    ) or "暂无近期记录"

    system = (
        "你是「贴心小护士」的问诊助手，专注于慢病健康管理。"
        "用温和、口语化的中文回答，不做诊断，只提供健康管理建议。"
        f"\n患者慢病：{', '.join(ctx.patient.diseases or ['未指定'])}"
        f"\n近期指标：\n{records_text}"
        f"\n\n参考知识：\n{context}"
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(ctx.history)
    messages.append({"role": "user", "content": message})
    return messages


async def consult_agent(ctx: AgentContext, message: str) -> str:
    start = time.time()
    messages = await build_consult_messages(ctx, message)
    reply = await llm_service.chat(messages)
    await ctx.log_trace("consult", "symptom_consultation", {"message": message}, {"reply": reply[:300]}, start)
    return reply


async def monitor_agent(ctx: AgentContext, message: str) -> str:
    start = time.time()
    health_svc = HealthService(ctx.db)
    recent = await health_svc.get_recent_records(ctx.patient.id, 10)
    abnormal = [r for r in recent if r.is_abnormal]
    output = {
        "total_records": len(recent),
        "abnormal_count": len(abnormal),
        "latest": [
            {"type": r.record_type.value, "value": r.value, "unit": r.unit, "abnormal": r.is_abnormal}
            for r in recent[:3]
        ],
    }
    await ctx.log_trace("monitor", "data_analysis", {}, output, start)
    if abnormal:
        return f"监测到您有 {len(abnormal)} 条异常指标。最近异常：{abnormal[0].record_type.value}={abnormal[0].value}{abnormal[0].unit}。建议关注并联系医生。"
    return f"已分析您最近 {len(recent)} 条健康记录，目前指标整体正常，请继续保持规律监测。"


async def build_planner_messages(ctx: AgentContext, message: str) -> list[dict]:
    context = ""
    if settings.enable_rag:
        rag = RAGService(ctx.db)
        disease = ctx.patient.diseases[0] if ctx.patient.diseases else "general"
        chunks = await rag.search(f"饮食运动方案 {disease}", disease=disease)
        context = rag.format_context(chunks)

    system = (
        "根据患者信息和指南知识，生成个性化慢病管理方案。"
        "以JSON格式回复，包含 diet_plan, exercise_plan, monitoring_plan 三个字段，每个字段为具体建议列表。"
        f"\n患者信息：慢病={ctx.patient.diseases}, 身高={ctx.patient.height_cm}, 体重={ctx.patient.weight_kg}"
        f"\n参考知识：\n{context}"
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(ctx.history)
    messages.append({"role": "user", "content": message or "请为我制定慢病管理方案"})
    return messages


async def create_care_plan(ctx: AgentContext, message: str, reply: str) -> dict:
    plan_data = {
        "diet_plan": {"items": ["低盐低脂饮食", "每日蔬菜500g", "控制精制碳水摄入", "少食多餐"]},
        "exercise_plan": {"items": ["每周150分钟中等强度有氧运动", "每日散步30分钟", "避免剧烈运动"]},
        "monitoring_plan": {"items": ["每日监测血压", "每周监测血糖3次", "每月体重记录"]},
        "ai_notes": reply,
    }
    care_plan = CarePlan(
        patient_id=ctx.patient.id,
        title="个性化慢病管理方案",
        diet_plan=plan_data["diet_plan"],
        exercise_plan=plan_data["exercise_plan"],
        monitoring_plan=plan_data["monitoring_plan"],
        medication_notes="请遵医嘱用药，不可自行调整。",
        created_by_agent="planner",
    )
    ctx.db.add(care_plan)
    await ctx.db.flush()
    plan_data["plan_id"] = care_plan.id
    return plan_data


async def planner_agent(ctx: AgentContext, message: str) -> dict:
    start = time.time()
    messages = await build_planner_messages(ctx, message)
    reply = await llm_service.chat(messages)
    plan_data = await create_care_plan(ctx, message, reply)
    await ctx.log_trace("planner", "create_care_plan", {"message": message}, plan_data, start)
    return plan_data


async def followup_agent(ctx: AgentContext, message: str) -> dict:
    start = time.time()
    questions = [
        {"id": "q1", "text": "本周是否按时服药？", "type": "boolean"},
        {"id": "q2", "text": "每日监测指标的频率如何？", "type": "choice", "options": ["每天", "每周几次", "很少"]},
        {"id": "q3", "text": "饮食和运动计划执行情况？", "type": "scale", "min": 1, "max": 5},
    ]
    followup = FollowUp(
        patient_id=ctx.patient.id,
        title="本周慢病管理随访",
        questions=questions,
        status="pending",
    )
    ctx.db.add(followup)
    await ctx.db.flush()
    output = {"followup_id": followup.id, "questions": questions}
    await ctx.log_trace("followup", "create_followup", {}, output, start)
    return output


async def warning_agent(ctx: AgentContext, message: str) -> str:
    start = time.time()
    from app.services.alert_service import AlertService

    alert_svc = AlertService(ctx.db)
    alerts = await alert_svc.list_alerts(ctx.patient.id, unresolved_only=True)
    output = {"unresolved_count": len(alerts), "highest_level": alerts[0].level.value if alerts else "green"}
    await ctx.log_trace("warning", "risk_assessment", {}, output, start)
    if not alerts:
        return "当前没有未处理的健康预警，您的指标整体稳定。请继续保持规律监测。"
    top = alerts[0]
    return f"您有 {len(alerts)} 条待处理预警。最近：【{top.level.value}】{top.title} - {top.message}。建议：{top.suggestion}"


async def run_agent_graph(db: AsyncSession, patient: Patient, message: str, session_id: str | None = None) -> dict[str, Any]:
    is_new_session = not session_id
    session_id = session_id or str(uuid.uuid4())
    history = await load_history(db, patient.id, session_id)
    ctx = AgentContext(db, patient, session_id, history=history)

    await save_message(db, patient.id, session_id, "user", message)
    if is_new_session:
        await enforce_session_limit(db, patient.id)

    # 病历识别优先于红旗分流：病历是历史记录，"胸痛"等词不应触发急症回复。
    if looks_like_medical_record(message):
        reply, llm_mode = await document_agent(ctx, message)
        await save_message(db, patient.id, session_id, "assistant", reply)
        await redis_client.set_patient_context(patient.id, {
            "session_id": session_id,
            "last_intent": "document",
            "diseases": patient.diseases,
        })
        return {
            "reply": reply, "session_id": session_id, "agent_traces": ctx.traces,
            "care_plan": None, "followup": None, "intent": "document", "llm_mode": llm_mode,
        }

    intent = await router_agent(ctx, message)
    reply = ""
    care_plan = None
    followup = None

    if intent == "consult":
        reply = await consult_agent(ctx, message)
        if any(k in message for k in ["头晕", "不舒服", "怎么办"]):
            care_plan = await planner_agent(ctx, "根据当前症状调整管理方案")
    elif intent == "monitor":
        reply = await monitor_agent(ctx, message)
    elif intent == "planner":
        care_plan = await planner_agent(ctx, message)
        reply = llm_service.DISCLAIMER + "\n\n已为您生成个性化管理方案，请查看「管理方案」页面。"
    elif intent == "followup":
        followup = await followup_agent(ctx, message)
        reply = "已为您创建随访任务，请前往「随访任务」页面完成问卷。"
    elif intent == "warning":
        reply = await warning_agent(ctx, message)
    else:
        reply = await consult_agent(ctx, message)

    await save_message(db, patient.id, session_id, "assistant", reply)

    await redis_client.set_patient_context(patient.id, {
        "session_id": session_id,
        "last_intent": intent,
        "diseases": patient.diseases,
    })

    return {
        "reply": reply,
        "session_id": session_id,
        "agent_traces": ctx.traces,
        "care_plan": care_plan,
        "followup": followup,
        "intent": intent,
    }
