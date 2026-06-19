import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentTrace, CarePlan, FollowUp, Patient
from app.services.health_service import HealthService
from app.services.llm_service import llm_service
from app.services.rag_service import RAGService
from app.services.redis_client import redis_client


class AgentContext:
    def __init__(self, db: AsyncSession, patient: Patient, session_id: str):
        self.db = db
        self.patient = patient
        self.session_id = session_id
        self.traces: list[dict] = []

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


async def consult_agent(ctx: AgentContext, message: str) -> str:
    start = time.time()
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

    messages = [
        {
            "role": "system",
            "content": (
                "你是「贴心小护士」的问诊助手，专注于慢病健康管理。"
                "用温和、口语化的中文回答，不做诊断，只提供健康管理建议。"
                f"\n患者慢病：{', '.join(ctx.patient.diseases or ['未指定'])}"
                f"\n近期指标：\n{records_text}"
                f"\n\n参考知识：\n{context}"
            ),
        },
        {"role": "user", "content": message},
    ]
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


async def planner_agent(ctx: AgentContext, message: str) -> dict:
    start = time.time()
    rag = RAGService(ctx.db)
    disease = ctx.patient.diseases[0] if ctx.patient.diseases else "general"
    chunks = await rag.search(f"饮食运动方案 {disease}", disease=disease)
    context = rag.format_context(chunks)

    messages = [
        {
            "role": "system",
            "content": (
                "根据患者信息和指南知识，生成个性化慢病管理方案。"
                "以JSON格式回复，包含 diet_plan, exercise_plan, monitoring_plan 三个字段，每个字段为具体建议列表。"
                f"\n患者信息：慢病={ctx.patient.diseases}, 身高={ctx.patient.height_cm}, 体重={ctx.patient.weight_kg}"
                f"\n参考知识：\n{context}"
            ),
        },
        {"role": "user", "content": message or "请为我制定慢病管理方案"},
    ]
    reply = await llm_service.chat(messages)

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
    session_id = session_id or str(uuid.uuid4())
    ctx = AgentContext(db, patient, session_id)

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
