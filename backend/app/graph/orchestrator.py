"""Agent 协调器：唯一运行时入口（handle_message / handle_stream）。

拓扑（规格 §5 / §6）：
    Safety → Router → Consult / Monitor / Planner / Document
    （Medication、Diagnosis 为阶段 2/3，本阶段只保留占位函数，不路由）

约定：
- 所有 agent 返回 AgentResult（app.graph.state），禁止裸 dict；
- 红旗、确认词、120 判断全部走规则，不交给 LLM；
- needs_confirmation / safety_120 写入 PendingStore（Redis，TTL 600s）；
- 无 LLM Key 时沿用 llm_service 的 Mock 兜底。
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph.context_builder import build_context_messages
from app.graph.presentation import build_presentation, to_tts_text
from app.graph.state import Action, AgentResult, Evidence, PendingStore, Presentation, make_result
from app.models import (
    AgentTrace,
    CarePlan,
    ChatMessage,
    Disease,
    DiseaseSymptom,
    MedicationLog,
    Patient,
    RecordType,
    Symptom,
)
from app.schemas import HealthRecordCreate, MedicationReminderCreate
from app.services.alert_service import AlertService
from app.services.document_processing import DocumentService
from app.services.document_parser import (
    extract_lab_metrics,
    extract_prescription_medications,
    format_medical_record_modules,
    summarize_medical_record,
)
from app.services.drug_service import DrugSafetyService
from app.services.health_service import HealthService
from app.services.llm_service import llm_service
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.redis_client import redis_client
from app.services.reminder_service import ReminderService

HISTORY_LIMIT = 10
SESSION_LIMIT = 20

VALID_RECORD_TYPES = {e.value for e in RecordType}

RECORD_TYPE_LABELS = {
    "blood_glucose": "血糖",
    "blood_pressure": "血压",
    "weight": "体重",
    "heart_rate": "心率",
    "blood_lipid": "血脂",
    "spo2": "血氧",
}

CONTEXT_LABELS = {
    "fasting": "空腹",
    "postprandial": "餐后2h",
    "random": "随机",
    "bedtime": "睡前",
    "ldl": "低密度脂蛋白",
    "tc": "总胆固醇",
    "tg": "甘油三酯",
    "hdl": "高密度脂蛋白",
}

# ---- 病历识别（沿用旧约定：病历优先于红旗分流） ----
DOCUMENT_MARKERS = (
    "主诉", "现病史", "既往史", "家族史", "体格检查", "辅助检查",
    "诊断依据", "治疗方案", "出院医嘱", "入院诊断", "出院诊断",
    "入院日期", "出院日期", "治疗经过", "实验室检查", "影像学检查",
)

# ---- Safety 规则 ----
RED_FLAG_TERMS = (
    "胸痛", "胸口疼", "胸口痛", "心口疼", "心口痛", "胸口压榨", "胸闷",
    "呼吸困难", "喘不上气", "憋气", "晕厥", "晕倒", "昏倒", "意识不清",
    "口角歪斜", "说话不清", "大舌头", "半边身子", "单侧手脚", "半边无力",
    "单侧麻", "剧烈头痛", "抽搐", "呕血", "黑便", "喉头水肿",
)
NEGATION_WORDS = ("没有", "不", "没", "无")

SAFETY_REVIEW_SYSTEM = (
    "你是医疗安全分诊助手。判断用户这句话是否描述「当前、本人、真实、急性」的危险信号。\n"
    "只输出 JSON：\n"
    '{"is_emergency": true/false, "severity": "red|orange|none", '
    '"belongs_to": "self|other|past|hypothetical", "reason": "一句话"}'
)

# ---- Router ----
METRIC_WORDS = (
    "血糖", "血压", "高压", "低压", "心率", "脉搏",
    "血氧", "体重", "血脂", "低密度", "胆固醇", "甘油三酯",
)
SYMPTOM_KEYS = ("头晕", "不舒服", "怎么办")

# ---- Medication 抽取（无 LLM Key 时的正则兜底） ----
MED_FORM_RE = re.compile(
    r"(?:加|开|吃|服用|添加)\s*(?:了|点)?\s*"
    r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}?(?:片|胶囊|颗粒|丸|注射液|口服液|软膏|滴眼液|喷雾|贴剂|散))"
)
MED_PLAIN_RE = re.compile(r"(?:加|开|吃|服用|添加)\s*(?:了|点)?\s*([\u4e00-\u9fa5]{2,12})")
DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg|毫克|g|克|片|粒|ml|毫升|袋|支|单位)", re.I
)
FREQ_WORDS = [
    ("qd", ("每天一次", "每日一次", "一日一次", "一天一次", "每天1次", "每日1次", "qd")),
    ("bid", ("每天两次", "每日两次", "一日两次", "一天两次", "每天2次", "每日2次", "bid")),
    ("tid", ("每天三次", "每日三次", "一日三次", "一天三次", "每天3次", "每日3次", "tid")),
    ("qid", ("每天四次", "每日四次", "一日四次", "一天四次", "每天4次", "每日4次", "qid")),
    ("qn", ("睡前", "qn")),
    ("prn", ("按需", "prn")),
]
FREQ_LABELS = {
    "qd": "每日1次",
    "bid": "每日2次",
    "tid": "每日3次",
    "qid": "每日4次",
    "q8h": "每8小时",
    "qn": "睡前",
    "prn": "按需",
}

# ---- 确认 / 拒绝词 ----
CONFIRM_WORDS = ("确认", "对", "好", "是", "可以", "行", "没错", "嗯", "记下来", "保存")
CANCEL_STRONG = ("取消", "不对", "不是", "不确认", "算了", "重来", "不要", "不用", "别", "不")
YES_WORDS = ("要", "需要", "好", "是", "拨打", "打", "行", "可以", "嗯")
NO_WORDS = ("不用", "不要", "不需要", "不", "没", "算了", "没事")


def looks_like_medical_record(message: str) -> bool:
    """聊天粘贴病历识别：长度 ≥80 且命中 ≥2 个结构标记词。"""
    if len(message) < 80:
        return False
    return sum(1 for marker in DOCUMENT_MARKERS if marker in message) >= 2


def looks_like_metric_report(message: str) -> bool:
    """是否像「报指标」：含指标词 + 数字，且不是长病历。"""
    if len(message) > 120:
        return False
    return any(w in message for w in METRIC_WORDS) and bool(re.search(r"\d", message))


# ---- IO_SPEC §2：输入意图细分 ----
METRIC_QUESTION_WORDS = (
    "算高吗", "算低吗", "高吗", "低吗", "正常吗", "怎么样", "咋样",
    "严重吗", "要紧吗", "是否", "是不是", "吗", "？", "?",
)
METRIC_WRITE_WORDS = ("记录", "记一下", "帮我记", "录入", "保存", "添加", "写进")
MED_INTAKE_WORDS = ("吃了", "刚吃", "服用了", "吃过", "喝了一片", "已服", "吃过了")
MED_REMINDER_WORDS = (
    "以后", "每天", "每日", "长期", "帮我加", "加药", "开药", "添加用药",
    "设置提醒", "设个闹钟", "设个提醒", "闹钟", "提醒", "要开始吃", "从今天起", "规律吃",
)
MED_QUESTION_WORDS = (
    "怎么吃", "饭前", "饭后", "漏服", "副作用", "能一起吃", "可以吃吗",
    "忌口", "注意什么", "什么时候吃", "说明书", "能不能吃",
)
PILLBOX_WORDS = ("药盒照片", "拍药盒", "拍个药盒", "扫条码", "条形码", "药瓶照片", "拍照识药")
SMALLTALK_WORDS = ("嗯", "在吗", "你好", "您好", "谢谢", "好的", "在么")
EMOTION_WORDS = ("害怕", "怕", "焦虑", "担心", "紧张", "心里难受", "想哭", "睡不着")


def is_metric_question(message: str) -> bool:
    """询问数字（如「血糖 6.8 算高吗」）不触发二次确认。"""
    return any(w in message for w in METRIC_QUESTION_WORDS) and not any(
        w in message for w in METRIC_WRITE_WORDS
    )


def is_medication_intake(message: str) -> bool:
    return any(w in message for w in MED_INTAKE_WORDS)


def is_medication_reminder(message: str) -> bool:
    return any(w in message for w in MED_REMINDER_WORDS)


def is_medication_question(message: str) -> bool:
    return any(w in message for w in MED_QUESTION_WORDS)


def is_pillbox_request(message: str) -> bool:
    return any(w in message for w in PILLBOX_WORDS)


def is_smalltalk(message: str) -> bool:
    text = _norm(message)
    return bool(text) and (text in SMALLTALK_WORDS or (len(text) <= 2 and text in ("嗯", "哦", "好")))


def is_emotion(message: str) -> bool:
    return any(w in message for w in EMOTION_WORDS)


def medication_mode(message: str) -> str:
    """intake / reminder / query / pillbox。"""
    if is_pillbox_request(message):
        return "pillbox"
    if any(w in message for w in ("帮我加", "帮我开", "设置提醒", "设个闹钟", "设个提醒", "添加用药", "开药")):
        return "reminder"
    if is_medication_question(message) and not any(
        w in message for w in ("帮我加", "设置", "建个", "添加", "开药")
    ):
        return "query"
    if is_medication_intake(message) and not is_medication_reminder(message):
        return "intake"
    if is_medication_reminder(message):
        return "reminder"
    return "query"

def recall_red_flags(message: str) -> list[dict]:
    """L1 规则召回：返回 [{term, negated}]，否定窗口为命中词前 6 字。"""
    hits: list[dict] = []
    for term in RED_FLAG_TERMS:
        start = 0
        while True:
            idx = message.find(term, start)
            if idx < 0:
                break
            window = message[max(0, idx - 6):idx]
            hits.append({"term": term, "negated": any(w in window for w in NEGATION_WORDS)})
            start = idx + len(term)
    return hits


def _norm(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?~～]+", "", text or "")


def is_cancel(text: str) -> bool:
    t = _norm(text)
    return bool(t) and any(w in t for w in CANCEL_STRONG)


def is_confirm(text: str) -> bool:
    t = _norm(text)
    if not t or is_cancel(t):
        return False
    return any(w in t for w in CONFIRM_WORDS)


def is_no(text: str) -> bool:
    t = _norm(text)
    return bool(t) and any(w in t for w in NO_WORDS)


def is_yes(text: str) -> bool:
    t = _norm(text)
    if not t or is_no(t):
        return False
    return any(w in t for w in YES_WORDS)


def ensure_disclaimer(text: str) -> str:
    if not text:
        return llm_service.DISCLAIMER
    if llm_service.DISCLAIMER in text:
        return text
    return f"{text}\n\n{llm_service.DISCLAIMER}"


def _chunks_to_evidence(chunks: list[dict]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for c in chunks:
        evidence.append(
            {
                "source": str(c.get("source", "")),
                "title": str(c.get("title", "")),
                "snippet": str(c.get("content", ""))[:120],
                "score": float(c.get("score", 0) or 0),
            }
        )
    return evidence


# ======================================================================
# 会话历史 / 上下文
# ======================================================================


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


async def _latest_session_id(db: AsyncSession, patient_id: int) -> str | None:
    result = await db.execute(
        select(ChatMessage.session_id)
        .where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _save_context(patient: Patient, session_id: str, intent: str | None) -> None:
    try:
        await redis_client.set_patient_context(
            patient.id,
            {"session_id": session_id, "last_intent": intent, "diseases": patient.diseases},
        )
    except Exception:
        pass


class AgentContext:
    def __init__(self, db: AsyncSession, patient: Patient, session_id: str, history: list[dict] | None = None):
        self.db = db
        self.patient = patient
        self.session_id = session_id
        self.traces: list[dict] = []
        self.history = history or []

    async def log_trace(
        self,
        agent_name: str,
        action: str,
        input_data: dict,
        output_data: dict,
        start: float,
        *,
        status: str = "ok",
        evidence: list[dict] | None = None,
        fallback: bool = False,
        error: str | None = None,
    ):
        duration = int((time.time() - start) * 1000)
        payload: dict[str, Any] = dict(output_data or {})
        payload.setdefault("status", status)
        payload["model"] = settings.llm_model if llm_service.is_available else "mock"
        payload["fallback"] = bool(fallback or not llm_service.is_available)
        if evidence:
            payload["evidence"] = evidence
        if error:
            payload["error"] = error

        trace = AgentTrace(
            patient_id=self.patient.id,
            session_id=self.session_id,
            agent_name=agent_name,
            action=action,
            input_data=input_data,
            output_data=payload,
            duration_ms=duration,
        )
        self.db.add(trace)
        await self.db.flush()
        self.traces.append(
            {
                "agent": agent_name,
                "action": action,
                "duration_ms": duration,
                "status": status,
                "output_summary": str(payload)[:200],
            }
        )


# ======================================================================
# Safety
# ======================================================================


def _format_history(history: list[dict], limit: int = 2) -> str:
    rows = history[-limit:] if history else []
    return "\n".join(f"{m.get('role')}: {str(m.get('content', ''))[:80]}" for m in rows) or "无"


async def _llm_safety_review(message: str, terms: list[str], history: list[dict]) -> dict | None:
    if not llm_service.is_available:
        return None
    user = (
        f"用户原话：{message}\n"
        f"命中词：{'、'.join(terms)}\n"
        f"最近对话：\n{_format_history(history)}"
    )
    try:
        return await llm_service.extract_json(SAFETY_REVIEW_SYSTEM, user)
    except Exception:
        return None


def decide_safety(hits: list[dict], review: dict | None) -> tuple[bool, str, str]:
    """规则与 LLM 复核的统一决策入口：返回 (blocked, decision, reason)。"""
    if not hits:
        return False, "pass", "no_hits"
    if review is None:
        # 无 Key / LLM 失败：规则保守判断；全是否定词时放行（可解释）
        all_negated = all(h.get("negated") for h in hits)
        blocked = not all_negated
        return blocked, ("blocked_rule" if blocked else "pass_negated"), "llm_unavailable_rule_fallback"
    emergency = bool(review.get("is_emergency"))
    severity = str(review.get("severity", "none"))
    belongs = str(review.get("belongs_to", "self"))
    blocked = emergency and severity in ("red", "orange") and belongs == "self"
    return blocked, ("blocked_llm" if blocked else "pass_llm"), str(review.get("reason", ""))


async def safety_agent(ctx: AgentContext, message: str) -> AgentResult:
    """三层漏斗：规则召回 → LLM 复核 → 决策（规格 §5.1）。"""
    start = time.time()
    hits = recall_red_flags(message)
    if not hits:
        await ctx.log_trace(
            "safety", "red_flag_screen", {"message": message[:200]},
            {"hits": [], "decision": "pass"}, start,
            fallback=not llm_service.is_available,
        )
        return make_result("safety", reply="", payload={"is_emergency": False, "hits": []})

    terms = [h["term"] for h in hits]
    review = await _llm_safety_review(message, terms, ctx.history)
    blocked, decision, reason = decide_safety(hits, review)

    await ctx.log_trace(
        "safety", "red_flag_screen",
        {"message": message[:200], "hits": hits},
        {"decision": decision, "review": review, "blocked": blocked, "reason": reason},
        start, status="blocked" if blocked else "ok",
        fallback=review is None,
    )

    if blocked:
        reply = "这可能是紧急情况，请立即拨打 120 或马上就医。需要我帮您拨打 120 吗？"
        return make_result(
            "safety",
            status="blocked",
            reply=reply,
            payload={"kind": "safety_120", "red_flags": terms},
            presentation=build_presentation(
                "safety",
                reply,
                summary="可能是紧急情况",
                key_points=["请立即拨打 120 或马上就医", "不要自行驾车或在家等待"],
                action_items=["立即拨打 120，或让家人陪同就医"],
                boundary="这是紧急情况，请立即就医；不要自行用药或等待。",
                tts_text="这可能是紧急情况。请立即拨打 120，或马上就医。",
                emergency=True,
            ),
        )
    return make_result(
        "safety", reply="",
        payload={"is_emergency": False, "hits": hits, "review": review},
    )


# ======================================================================
# Router
# ======================================================================


def classify_intent(message: str) -> str:
    """规则优先的意图分类（IO_SPEC §2.1 映射；LLM 兜底未启用，SPEC-GAP）。"""
    msg = message.lower()
    if looks_like_medical_record(message):
        return "document"
    if is_pillbox_request(message) or is_medication_intake(message) or is_medication_reminder(message):
        return "medication"
    if is_medication_question(message):
        return "consult"
    # 数据录入：明确「录入/记录/数据」，或「指标词 + 数字」的报数说法。
    if any(k in msg for k in ("录入", "记录", "数据", "记一下", "帮我记")):
        return "monitor"
    if looks_like_metric_report(message):
        return "monitor"
    # 问自己的数据（无数字也算）：我最近血糖咋样 / 我的血压高吗
    if any(w in msg for w in ("我最近", "我的", "咋样", "怎么样", "趋势", "控制得")) and any(
        w in msg for w in METRIC_WORDS
    ):
        return "monitor"
    if any(k in msg for k in ("诊断", "什么病", "得了什么", "可能是什么")):
        return "diagnosis"
    if any(k in msg for k in ("方案", "计划", "饮食", "运动", "建议")):
        return "planner"
    if any(k in msg for k in ("随访", "复查", "依从", "预警", "异常", "危险")):
        return "consult"
    return "consult"


async def router_agent(ctx: AgentContext, message: str) -> AgentResult:
    start = time.time()
    intent = classify_intent(message)
    await ctx.log_trace(
        "router", "intent_classification", {"message": message[:200]},
        {"intent": intent}, start,
    )
    return make_result("router", reply="", payload={"intent": intent})


# ======================================================================
# Consult
# ======================================================================


async def build_consult_messages(
    ctx: AgentContext, message: str, alert_context: str | None = None
) -> tuple[list[dict], list[Evidence]]:
    evidence: list[Evidence] = []
    if settings.enable_rag:
        rag = RAGService(ctx.db)
        disease = ctx.patient.diseases[0] if ctx.patient.diseases else None
        chunks = await rag.search(message, disease=disease)
        evidence = _chunks_to_evidence(chunks)

    health_svc = HealthService(ctx.db)
    recent = await health_svc.get_recent_records(ctx.patient.id, 5)
    records_text = "\n".join(
        f"- {r.record_type.value}: {r.value}{r.unit} ({r.recorded_at.strftime('%Y-%m-%d')})"
        for r in recent
    ) or "暂无近期记录"

    alerts_text = alert_context or ""
    if not alerts_text and any(k in message for k in ("预警", "异常", "危险")):
        alerts = await AlertService(ctx.db).list_alerts(ctx.patient.id, unresolved_only=True)
        alerts_text = "\n".join(
            f"- [{a.level.value}] {a.title}：{a.message}" for a in alerts[:5]
        ) or "暂无未处理预警"

    patient_context = (
        f"慢病：{', '.join(ctx.patient.diseases or ['未指定'])}\n"
        f"过敏史：{ctx.patient.allergies or '无记录'}\n"
        f"近期指标：\n{records_text}"
    )
    if alerts_text:
        patient_context += f"\n\n当前预警：\n{alerts_text}"

    messages = build_context_messages(
        role=(
            "你是「贴心小护士」的问诊助手，专注于慢病健康管理。"
            "用温和、口语化的中文回答，不做诊断，只提供健康管理建议。"
        ),
        patient_context=patient_context,
        evidence=evidence,
        history=ctx.history,
        task=message,
        output_hint="输出健康管理建议，不做诊断，必须包含免责声明。",
    )
    return messages, evidence


async def consult_agent(
    ctx: AgentContext, message: str, alert_context: str | None = None
) -> AgentResult:
    start = time.time()
    if is_smalltalk(message):
        reply = "我在的，您慢慢说。今天想先聊哪件事？"
        await ctx.log_trace(
            "consult", "smalltalk", {"message": message[:200]}, {"reply": reply}, start,
        )
        return make_result(
            "consult",
            reply=reply,
            presentation=build_presentation(
                "consult", reply,
                summary="我在，慢慢说",
                key_points=["可以直接说哪里不舒服", "也可以让我帮您记录指标"],
                action_items=["把想问的事说出来即可"],
            ),
        )

    messages, evidence = await build_consult_messages(ctx, message, alert_context)
    raw_reply = await llm_service.chat(messages)
    if is_emotion(message):
        raw_reply = "先别着急，我在。" + raw_reply
    reply = ensure_disclaimer(raw_reply)
    await ctx.log_trace(
        "consult", "symptom_consultation", {"message": message[:200]},
        {"reply": reply[:300]}, start,
        evidence=evidence, fallback=not llm_service.is_available,
    )
    presentation = build_presentation(
        "consult",
        reply,
        key_points=[str(e.get("title") or e.get("source") or "") for e in evidence[:3]],
        action_items=None,
    )
    result = make_result("consult", reply=reply, evidence=evidence, presentation=presentation)
    # 症状明显时附带生成管理方案（沿用旧行为）
    if any(k in message for k in SYMPTOM_KEYS):
        plan = await planner_agent(ctx, "根据当前症状调整管理方案")
        result["actions"] = plan.get("actions", [])
        result["evidence"] = list(result.get("evidence", [])) + list(plan.get("evidence", []))
        result["payload"] = {"care_plan": (plan.get("payload") or {}).get("care_plan")}
    return result


# ======================================================================
# Monitor
# ======================================================================


def _normalize_metric(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    record_type = raw.get("record_type")
    if record_type not in VALID_RECORD_TYPES:
        return None
    try:
        value = float(raw.get("value"))
    except (TypeError, ValueError):
        return None
    metric: dict[str, Any] = {
        "record_type": record_type,
        "value": value,
        "unit": str(raw.get("unit") or ""),
        "name": str(raw.get("name") or RECORD_TYPE_LABELS.get(record_type, record_type)),
    }
    if raw.get("context"):
        metric["context"] = str(raw["context"])
    if record_type == "blood_pressure":
        try:
            systolic = float(raw.get("systolic")) if raw.get("systolic") is not None else value
            diastolic = (
                float(raw.get("diastolic")) if raw.get("diastolic") is not None else None
            )
        except (TypeError, ValueError):
            return None
        metric["systolic"] = systolic
        metric["diastolic"] = diastolic
        metric["value"] = systolic
    return metric


async def extract_metrics(text: str) -> list[dict]:
    """LLM 优先、正则兜底（复用 document_parser），只抽取不写库。"""
    try:
        raw_metrics = await extract_lab_metrics(text)
    except Exception:
        raw_metrics = []
    metrics: list[dict] = []
    for raw in raw_metrics:
        normalized = _normalize_metric(raw)
        if normalized:
            metrics.append(normalized)

    # 去重：同一指标/数值只保留一份；有场景（空腹/餐后等）时优先保留带场景的
    groups: dict[tuple, list[dict]] = {}
    for metric in metrics:
        groups.setdefault((metric["record_type"], metric["value"]), []).append(metric)
    deduped: list[dict] = []
    for group in groups.values():
        with_context = [m for m in group if m.get("context")]
        deduped.extend(with_context if with_context else group[:1])
    return deduped


def describe_metrics(metrics: list[dict]) -> str:
    parts: list[str] = []
    for m in metrics:
        record_type = m.get("record_type")
        unit = str(m.get("unit") or "")
        if record_type == "blood_pressure":
            diastolic = m.get("diastolic")
            if diastolic is None:
                parts.append(f"血压 {m.get('systolic')} {unit}".strip())
            else:
                parts.append(f"血压 {m.get('systolic')}/{diastolic} {unit}".strip())
        else:
            prefix = CONTEXT_LABELS.get(str(m.get("context")), "")
            parts.append(
                f"{prefix}{m.get('name') or record_type} {m.get('value')} {unit}".strip()
            )
    return "，".join(parts)


def _metric_payload(metric: dict) -> dict:
    extra: dict[str, Any] = {}
    if metric.get("record_type") == "blood_pressure":
        extra["systolic"] = metric.get("systolic")
        extra["diastolic"] = metric.get("diastolic")
    elif metric.get("context"):
        extra["type"] = metric["context"]
    return {
        "record_type": metric.get("record_type"),
        "value": metric.get("value"),
        "unit": metric.get("unit", ""),
        "extra_data": extra,
        "name": metric.get("name"),
        "context": metric.get("context"),
    }


async def monitor_agent(ctx: AgentContext, message: str, mode: str = "auto") -> AgentResult:
    if mode == "extract" or (
        mode == "auto" and looks_like_metric_report(message) and not is_metric_question(message)
    ):
        return await _monitor_extract(ctx, message)
    return await _monitor_analysis(ctx, message)


def _judge_metric(metric: dict) -> str:
    record_type = metric.get("record_type")
    value = metric.get("value")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "需要结合参考范围判断"
    if record_type == "blood_glucose":
        context = metric.get("context")
        if number < 3.9:
            return "偏低"
        if context == "postprandial":
            return "在目标范围内" if number <= 7.8 else "偏高"
        if number <= 6.1:
            return "在目标范围内"
        return "略高于目标" if number <= 7.0 else "偏高"
    if record_type == "blood_pressure":
        systolic = float(metric.get("systolic") or number)
        diastolic = float(metric.get("diastolic") or 0)
        if systolic >= 140 or diastolic >= 90:
            return "偏高"
        if systolic < 90 or (diastolic and diastolic < 60):
            return "偏低"
        return "在目标范围内"
    if record_type == "heart_rate":
        if number < 60:
            return "偏慢"
        if number > 100:
            return "偏快"
        return "在正常范围内"
    if record_type == "spo2":
        if number < 90:
            return "明显偏低，需要尽快就医"
        if number < 95:
            return "偏低"
        return "在正常范围内"
    return "需要结合参考范围判断"


async def _monitor_analysis(ctx: AgentContext, message: str) -> AgentResult:
    start = time.time()
    if is_metric_question(message):
        asked = await extract_metrics(message)
        if asked:
            metric = asked[0]
            desc = describe_metrics([metric])
            judgement = _judge_metric(metric)
            reply = f"您问的{desc}，{judgement}。单次结果仅供参考，建议继续监测，持续异常请就医。"
            await ctx.log_trace(
                "monitor", "metric_question", {"message": message[:200]},
                {"metric": metric, "judgement": judgement}, start,
            )
            return make_result(
                "monitor",
                reply=reply,
                presentation=build_presentation(
                    "monitor", reply,
                    summary=f"{judgement}"[:20],
                    key_points=[desc, "单次结果不能替代医生判断"],
                    action_items=["继续按计划监测", "持续异常请就医"],
                ),
            )

    recent = await HealthService(ctx.db).get_recent_records(ctx.patient.id, 10)
    abnormal = [r for r in recent if r.is_abnormal]
    output = {
        "total_records": len(recent),
        "abnormal_count": len(abnormal),
        "latest": [
            {"type": r.record_type.value, "value": r.value, "unit": r.unit, "abnormal": r.is_abnormal}
            for r in recent[:3]
        ],
    }
    evidence: list[Evidence] = []
    if recent:
        evidence.append(
            {
                "source": "近期记录",
                "title": f"近 {len(recent)} 条健康记录",
                "snippet": "；".join(
                    f"{r.record_type.value} {r.value}{r.unit}" for r in recent[:3]
                ),
            }
        )
    await ctx.log_trace(
        "monitor", "data_analysis", {"message": message[:200]}, output, start, evidence=evidence
    )
    if abnormal:
        top = abnormal[0]
        reply = (
            f"监测到您有 {len(abnormal)} 条异常指标。"
            f"最近异常：{top.record_type.value}={top.value}{top.unit}。建议关注并联系医生。"
        )
        summary = "有异常指标需要关注"
        key_points = [
            f"{r.record_type.value} {r.value}{r.unit}"
            for r in abnormal[:3]
        ]
        actions = ["先复测一次异常指标", "把记录带给医生看"]
    else:
        reply = f"已分析您最近 {len(recent)} 条健康记录，目前指标整体正常，请继续保持规律监测。"
        summary = "指标整体正常"
        key_points = [
            f"{r.record_type.value} {r.value}{r.unit}"
            for r in recent[:3]
        ] or ["近期还没有记录"]
        actions = ["继续保持规律监测", "有变化及时就医"]
    return make_result(
        "monitor",
        reply=reply,
        evidence=evidence,
        presentation=build_presentation(
            "monitor", reply,
            summary=summary, key_points=key_points, action_items=actions,
        ),
    )


async def _monitor_extract(ctx: AgentContext, message: str) -> AgentResult:
    start = time.time()
    metrics = await extract_metrics(message)
    if not metrics:
        await ctx.log_trace(
            "monitor", "metric_extract", {"message": message[:200]},
            {"metrics": []}, start, fallback=not llm_service.is_available,
        )
        return make_result(
            "monitor",
            reply="没太听清，能再说一次吗？您可以说「空腹血糖 6.8」这样的格式。",
            payload={"metrics": []},
        )
    desc = describe_metrics(metrics)
    reply = f"我听到您说，{desc}，对吗？\n回复「确认」记录，或「取消」放弃。"
    await ctx.log_trace(
        "monitor", "metric_extract", {"message": message[:200]},
        {"metrics": metrics}, start, status="needs_confirmation",
        fallback=not llm_service.is_available,
    )
    return make_result(
        "monitor",
        status="needs_confirmation",
        reply=reply,
        payload={"metrics": metrics},
        presentation=build_presentation(
            "monitor", reply,
            summary=f"识别到{desc}"[:20],
            key_points=[desc, "确认后才会写入健康记录"],
            action_items=["确认无误后说「确认」", "识别有误请说「取消」并重说"],
        ),
    )


# ======================================================================
# Planner
# ======================================================================

DEFAULT_PLAN: dict[str, dict] = {
    "diet_plan": {"items": ["低盐低脂饮食", "每日蔬菜 500g", "控制精制碳水", "少食多餐"]},
    "exercise_plan": {"items": ["每周 150 分钟中等强度有氧运动", "每日散步 30 分钟", "避免剧烈运动"]},
    "monitoring_plan": {"items": ["每日监测血压", "每周监测血糖 3 次", "每月记录体重"]},
}


async def build_planner_messages(ctx: AgentContext, message: str) -> tuple[list[dict], list[Evidence]]:
    evidence: list[Evidence] = []
    if settings.enable_rag:
        rag = RAGService(ctx.db)
        disease = ctx.patient.diseases[0] if ctx.patient.diseases else "general"
        chunks = await rag.search(f"饮食运动方案 {disease}", disease=disease)
        evidence = _chunks_to_evidence(chunks)

    patient_context = (
        f"慢病={ctx.patient.diseases}, 身高={ctx.patient.height_cm}, 体重={ctx.patient.weight_kg}"
    )
    messages = build_context_messages(
        role="根据患者信息和指南知识，生成个性化慢病管理方案。",
        patient_context=patient_context,
        evidence=evidence,
        history=ctx.history,
        task=message or "请为我制定慢病管理方案",
        output_hint=(
            "只输出 JSON，不要其他文字："
            '{"diet_plan":{"items":[...]},"exercise_plan":{"items":[...]},'
            '"monitoring_plan":{"items":[...]}}'
        ),
    )
    return messages, evidence


def _plan_items(value: Any) -> list[str] | None:
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        items = [str(i).strip() for i in value["items"] if str(i).strip()]
        return items or None
    if isinstance(value, list):
        items = [str(i).strip() for i in value if str(i).strip()]
        return items or None
    return None


def _parse_plan(reply: str) -> tuple[dict, bool]:
    parsed = llm_service._parse_json(reply) if reply else None
    if not isinstance(parsed, dict):
        return {key: {"items": list(value["items"])} for key, value in DEFAULT_PLAN.items()}, True
    result: dict[str, dict] = {}
    missing = False
    for key in ("diet_plan", "exercise_plan", "monitoring_plan"):
        items = _plan_items(parsed.get(key))
        if items is None:
            missing = True
            items = list(DEFAULT_PLAN[key]["items"])
        result[key] = {"items": items}
    return result, missing


async def _planner_result(
    ctx: AgentContext, message: str, reply: str, evidence: list[Evidence], start: float
) -> AgentResult:
    plan_data, fallback = _parse_plan(reply)
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

    payload = {"care_plan": {**plan_data, "plan_id": care_plan.id}}
    actions: list[Action] = [
        {"type": "navigate", "target": "/me/plans", "summary": "查看管理方案"}
    ]
    full_reply = ensure_disclaimer(
        "已为您生成个性化慢病管理方案，可在「我的 - 管理方案」查看。"
    )
    await ctx.log_trace(
        "planner", "create_care_plan", {"message": message[:200]},
        {"plan_id": care_plan.id, "fallback": fallback}, start,
        evidence=evidence, fallback=fallback,
    )
    return make_result(
        "planner",
        reply=full_reply,
        payload=payload,
        actions=actions,
        evidence=evidence,
        presentation=build_presentation(
            "planner",
            full_reply,
            summary="已生成管理方案",
            key_points=(
                list(plan_data["diet_plan"]["items"][:1])
                + list(plan_data["exercise_plan"]["items"][:1])
                + list(plan_data["monitoring_plan"]["items"][:1])
            ),
            action_items=["按方案执行饮食和运动", "下次复诊带上监测记录"],
        ),
    )


async def planner_agent(ctx: AgentContext, message: str) -> AgentResult:
    start = time.time()
    messages, evidence = await build_planner_messages(ctx, message)
    reply = await llm_service.chat(messages)
    return await _planner_result(ctx, message, reply, evidence, start)


# ======================================================================
# Document
# ======================================================================


async def document_agent(ctx: AgentContext, message: str) -> AgentResult:
    start = time.time()
    result = await summarize_medical_record(message)
    if not result:
        await ctx.log_trace(
            "document", "medical_record_summary", {"message": message[:200]},
            {"failed": True}, start,
        )
        return make_result(
            "document",
            reply="抱歉，我暂时无法识别这份病历内容，请稍后重试或直接描述您的问题。",
            payload={"failed": True},
        )
    modules = result.get("modules") or {}
    module_text = format_medical_record_modules(modules)
    explanation = ensure_disclaimer("已按 8 个部分为您整理：\n\n" + module_text)
    what = "；".join(modules.get("what", {}).get("items", []))
    abnormal = modules.get("abnormal", {}).get("items", [])
    medications = modules.get("medications", {}).get("items", [])
    followup = modules.get("followup", {}).get("items", [])
    risk = modules.get("risk", {}).get("items", [])
    warnings = result.get("warnings") or []
    has_archiveable = not any(w.get("code") == "no_archiveable_fields" for w in warnings)
    if not has_archiveable or result.get("needs_retake"):
        await ctx.log_trace(
            "document", "medical_record_summary", {"message": message[:200]},
            {"doc_type": result.get("doc_type"), "no_archiveable": True}, start,
        )
        return make_result(
            "document",
            reply=explanation + "\n\n未识别到可归档信息，请补充或重新上传更清晰的原件。",
            payload={"doc_type": result.get("doc_type"), "modules": modules, "warnings": warnings},
            presentation=build_presentation(
                "document", explanation,
                summary=what[:20],
                key_points=(abnormal[:1] + medications[:1] + risk[:1])[:3],
                action_items=["补充或重新提供清晰原件", "先把这段解释给医生看"],
                boundary=(risk[0] if risk else "") + " 本解释不能替代医生诊断。",
            ),
        )

    reply = explanation + "\n\n如需归档，请回复「确认」；不归档请回复「取消」。"
    await ctx.log_trace(
        "document", "medical_record_summary", {"message": message[:200]},
        {"doc_type": result.get("doc_type"), "modules": list(modules.keys())}, start,
        status="needs_confirmation",
    )
    return make_result(
        "document",
        status="needs_confirmation",
        reply=reply,
        payload={
            "doc_type": result.get("doc_type"),
            "entities": result.get("summary") or {},
            "modules": modules,
            "warnings": warnings,
        },
        presentation=build_presentation(
            "document",
            reply,
            summary=what[:20],
            key_points=(abnormal[:1] + medications[:1] + risk[:1])[:3],
            action_items=["确认无误后回复「确认」归档", "不想归档请回复「取消」"],
            boundary=(risk[0] if risk else "") + " 本解释不能替代医生诊断。",
            tts_text=(
                f"这份病历主要是{what}。"
                f"最需要注意的是{abnormal[0] if abnormal else '按医嘱复查'}。"
                "如果需要归档，请说确认；不需要请说取消。"
            ),
        ),
    )


# ======================================================================
# Medication / Diagnosis（阶段占位）
# ======================================================================


def _extract_medications_regex(text: str) -> list[dict]:
    match = MED_FORM_RE.search(text) or MED_PLAIN_RE.search(text)
    if not match:
        return []
    name = match.group(1).strip()
    name = re.sub(r"^(?:了|点|一片|1片|半片|两片|一粒|1粒|片|粒)+", "", name).strip()
    if name in ("什么药", "用药", "药建议", "药"):
        return []
    if any(word in name for word in ("闹钟", "提醒", "药的")):
        return []
    dose = None
    dose_unit = None
    dose_match = DOSE_RE.search(text)
    if dose_match:
        try:
            dose = float(dose_match.group(1))
        except ValueError:
            dose = None
        dose_unit = dose_match.group(2)
    frequency = "qd"
    for key, words in FREQ_WORDS:
        if any(word in text for word in words):
            frequency = key
            break
    return [
        {
            "medication_name": name,
            "name": name,
            "dose": dose,
            "dose_unit": dose_unit,
            "frequency": frequency,
        }
    ]


async def extract_medications(text: str) -> list[dict]:
    """处方提示词优先，失败/无 Key 时正则兜底。"""
    try:
        raw_meds = await extract_prescription_medications(text)
    except Exception:
        raw_meds = []
    meds = [m for m in (_normalize_medication(x) for x in raw_meds) if m]
    if meds:
        return meds
    return _extract_medications_regex(text)


def _describe_medication(med: dict) -> str:
    name = str(med.get("medication_name") or med.get("name") or "")
    dose = med.get("dose")
    unit = str(med.get("dose_unit") or "")
    freq = FREQ_LABELS.get(str(med.get("frequency") or "qd"), "")
    parts = [name]
    if dose is not None:
        parts.append(f"{dose}{unit}")
    if freq:
        parts.append(freq)
    return " ".join(p for p in parts if p).strip()


async def medication_agent(ctx: AgentContext, message: str) -> AgentResult:
    """用药：已服 → 打卡日志；未来 → 提醒；咨询 → RAG；拍药盒 → 明确降级。"""
    start = time.time()
    mode = medication_mode(message)

    if mode == "pillbox":
        reply = (
            "目前还不支持拍药盒或扫条码识别药品。"
            "请把药盒上的药名、剂量、用法打字发给我，或手动输入，我再帮您核对。"
        )
        await ctx.log_trace(
            "medication", "pillbox_not_supported", {"message": message[:200]},
            {"supported": False}, start,
        )
        return make_result(
            "medication",
            reply=reply,
            payload={"capability": "pillbox_not_supported"},
            presentation=build_presentation(
                "medication", reply,
                summary="暂不支持拍药盒",
                key_points=["拍照/条码识别药品暂未开放", "可以发药名文字，我帮您核对"],
                action_items=["把药名、剂量、用法打字发给我"],
            ),
        )

    if mode == "query":
        result = await consult_agent(ctx, message)
        result["agent"] = "medication"
        return result

    meds = await extract_medications(message)
    if not meds:
        reply = "没太听清药名。请说「以后每天吃一片阿司匹林」或「吃了片阿司匹林」，我再帮您处理。"
        await ctx.log_trace(
            "medication", "medication_extract", {"message": message[:200]},
            {"medications": [], "mode": mode}, start, status="ok",
            fallback=not llm_service.is_available,
        )
        return make_result(
            "medication",
            reply=reply,
            payload={"medications": [], "mode": mode},
            presentation=build_presentation(
                "medication", reply,
                summary="没听清药名",
                key_points=["需要药名和用法", "已服和以后吃是两种记录"],
                action_items=["再说一次药名和剂量"],
            ),
        )

    summary = "、".join(_describe_medication(m) for m in meds)

    if mode == "intake":
        reply = (
            f"识别到您吃了 {summary}，确认后记入今天的服药记录。\n"
            "回复「确认」记录，或「取消」。"
        )
        await ctx.log_trace(
            "medication", "medication_intake", {"message": message[:200]},
            {"medications": meds}, start, status="needs_confirmation",
            fallback=not llm_service.is_available,
        )
        return make_result(
            "medication",
            status="needs_confirmation",
            reply=reply,
            payload={"medications": meds, "mode": "intake"},
            presentation=build_presentation(
                "medication", reply,
                summary="识别到服药记录"[:20],
                key_points=[summary, "确认后才写入今天的服药日志"],
                action_items=["确认无误说「确认」", "识别有误说「取消」"],
            ),
        )

    existing = [r for r in await ReminderService(ctx.db).list(ctx.patient.id) if r.active]
    issues = await DrugSafetyService(ctx.db).check(
        ctx.patient, meds, existing_reminders=existing
    )
    if issues:
        issue_text = "；".join(
            f"{item['title']}（{item['why']}）" for item in issues[:2]
        )
        reply = (
            f"我听到您要添加：{summary}。\n"
            f"用药安全提示：{issue_text}。\n"
            "回复「确认」添加，或「取消」。"
        )
        key_points = [f"{item['title']}：{item['why']}" for item in issues[:2]]
    else:
        reply = f"我听到您要添加：{summary}。\n回复「确认」添加，或「取消」。"
        key_points = [summary, "确认后才会创建用药提醒"]
    await ctx.log_trace(
        "medication", "medication_extract",
        {"message": message[:200]},
        {"medications": meds, "issues": issues, "mode": "reminder"},
        start, status="needs_confirmation", fallback=not llm_service.is_available,
    )
    return make_result(
        "medication",
        status="needs_confirmation",
        reply=reply,
        payload={"medications": meds, "issues": issues, "mode": "reminder"},
        presentation=build_presentation(
            "medication", reply,
            summary="识别到用药提醒"[:20],
            key_points=key_points,
            action_items=["确认无误说「确认」", "识别有误说「取消」"],
        ),
    )


SYMPTOM_ALIASES = {
    "头晕": "头晕头痛",
    "头痛": "头晕头痛",
    "头晕头痛": "头晕头痛",
    "胸闷": "胸闷气短",
    "气短": "胸闷气短",
    "胸闷气短": "胸闷气短",
    "乏力": "乏力",
    "没力气": "乏力",
    "疲劳": "乏力",
    "多饮": "多饮多尿",
    "多尿": "多饮多尿",
    "多食": "多饮多尿",
    "口干": "多饮多尿",
}
EXTRA_SYMPTOMS = ("咳嗽", "心悸", "水肿", "恶心", "呕吐", "失眠", "视物模糊")


def _extract_symptoms(message: str) -> list[str]:
    found: list[str] = []
    for phrase, canonical in SYMPTOM_ALIASES.items():
        if phrase in message and canonical not in found:
            found.append(canonical)
    for name in EXTRA_SYMPTOMS:
        if name in message and name not in found:
            found.append(name)
    return found


async def _diagnosis_directions(ctx: AgentContext, symptoms: list[str]) -> list[dict]:
    disease_rows = (await ctx.db.execute(select(Disease))).scalars().all()
    symptom_rows = (await ctx.db.execute(select(Symptom))).scalars().all()
    link_rows = (await ctx.db.execute(select(DiseaseSymptom))).scalars().all()

    disease_by_id = {d.id: d for d in disease_rows}
    symptom_by_id = {s.id: s.name for s in symptom_rows}
    by_disease: dict[int, list[str]] = {}
    for link in link_rows:
        name = symptom_by_id.get(link.symptom_id)
        if name and name in symptoms:
            by_disease.setdefault(link.disease_id, []).append(name)

    directions: list[dict] = []
    for disease_id, names in by_disease.items():
        disease = disease_by_id.get(disease_id)
        if not disease:
            continue
        directions.append(
            {
                "disease": disease.name,
                "code": disease.code,
                "symptoms": names,
                "score": len(names),
            }
        )
    directions.sort(key=lambda item: item["score"], reverse=True)
    return directions


def _format_diagnosis_reply(
    symptoms: list[str], directions: list[dict], evidence: list[Evidence]
) -> str:
    lines = [f"已识别症状：{'、'.join(symptoms)}", "", "【可能方向】（仅供参考，不是诊断）"]
    if directions:
        for index, direction in enumerate(directions[:3], 1):
            lines.append(
                f"{index}. {direction['disease']}：匹配症状 {'、'.join(direction['symptoms'])}"
            )
    else:
        lines.append("暂未匹配到明确方向，请补充症状持续时间、诱因和既往病史。")

    lines.append("\n【依据】")
    if evidence:
        for item in evidence[:4]:
            if item.get("source") == "知识图谱":
                lines.append(f"- {item.get('relation') or item.get('title')}")
            else:
                lines.append(f"- {item.get('title')}（{item.get('source')}）")
    else:
        lines.append("- 暂无可用依据")

    lines.append("\n【需要警惕】")
    lines.append(
        "若出现胸痛、呼吸困难、意识不清、口角歪斜、剧烈头痛、呕血或黑便，请立即就医或拨打 120。"
    )
    lines.append("\n【就医建议】")
    lines.append("建议携带近期监测记录到相应专科就诊，完善检查后由医生判断；不要仅凭本回复自行用药。")
    return ensure_disclaimer("\n".join(lines))


async def diagnosis_agent(ctx: AgentContext, message: str) -> AgentResult:
    """诊断：表型抽取 → 知识图谱 + RAG 匹配 → 证据融合（规格 §5.8 / §9）。"""
    start = time.time()
    symptoms = _extract_symptoms(message)
    if not symptoms:
        await ctx.log_trace(
            "diagnosis", "phenotype_extract", {"message": message[:200]},
            {"symptoms": []}, start,
        )
        return make_result(
            "diagnosis",
            reply=ensure_disclaimer(
                "请先描述具体症状（如头晕、头痛、乏力、胸闷）以及持续时间和诱因，我再帮您梳理可能方向。"
            ),
            payload={"symptoms": [], "directions": []},
            presentation=build_presentation(
                "diagnosis",
                "请先描述具体症状（如头晕、头痛、乏力、胸闷）以及持续时间和诱因，我再帮您梳理可能方向。",
                summary="信息不足，先补充症状",
                key_points=["说出具体症状", "补充持续时间和诱因"],
                action_items=["再描述一次症状和持续时间"],
                boundary="这只是信息收集，不是诊断；如有急症请立即就医。",
            ),
        )

    directions = await _diagnosis_directions(ctx, symptoms)
    evidence: list[Evidence] = []
    for direction in directions[:3]:
        relation = f"{direction['disease']} —has_symptom→ {'、'.join(direction['symptoms'])}"
        evidence.append(
            {
                "source": "知识图谱",
                "title": f"{direction['disease']}：匹配症状 {'、'.join(direction['symptoms'])}",
                "relation": relation,
                "snippet": relation,
            }
        )

    if settings.enable_rag:
        rag = RAGService(ctx.db)
        chunks = await rag.search(f"{' '.join(symptoms)} {message}", top_k=3)
        evidence.extend(_chunks_to_evidence(chunks))

    reply = _format_diagnosis_reply(symptoms, directions, evidence)
    reply = reply.replace("确诊", "考虑").replace("诊断为", "可能与").replace("就是", "可能是")
    await ctx.log_trace(
        "diagnosis", "phenotype_and_kg_match",
        {"message": message[:200]},
        {"symptoms": symptoms, "directions": directions},
        start, evidence=evidence,
    )
    top = directions[0]["disease"] if directions else ""
    return make_result(
        "diagnosis",
        reply=reply,
        payload={"symptoms": symptoms, "directions": directions},
        evidence=evidence,
        presentation=build_presentation(
            "diagnosis",
            reply,
            summary=(f"可能方向：{top}" if top else "暂未匹配明确方向")[:20],
            key_points=[
                f"{d['disease']}（{'、'.join(d['symptoms'])}）" for d in directions[:3]
            ] or [e.get("title", "") for e in evidence[:3]],
            action_items=["到相应专科就诊，完善检查", "出现危险信号立即就医"],
            boundary="以上只是可能方向，不是诊断；如出现胸痛、呼吸困难、意识不清等急症，请立即就医。",
            tts_text=(f"可能方向是{top}。" if top else "暂时没有匹配到明确方向。") + "建议到专科就诊，由医生判断。",
        ),
    )


# ======================================================================
# 分发 / 待确认执行
# ======================================================================


async def dispatch_intent(
    ctx: AgentContext, intent: str, message: str, alert_context: str | None = None
) -> AgentResult:
    if intent == "monitor":
        return await monitor_agent(ctx, message)
    if intent == "planner":
        return await planner_agent(ctx, message)
    if intent == "document":
        return await document_agent(ctx, message)
    if intent == "medication":
        return await medication_agent(ctx, message)
    if intent == "diagnosis":
        return await diagnosis_agent(ctx, message)
    return await consult_agent(ctx, message, alert_context)


async def _maybe_set_pending(
    ctx: AgentContext, result: AgentResult, intent: str | None, original_message: str
) -> None:
    if result.get("status") != "needs_confirmation":
        return
    await PendingStore.set(
        ctx.patient.id,
        ctx.session_id,
        {
            "kind": "confirm_write",
            "agent": result.get("agent", "monitor"),
            "original_message": original_message,
            "original_intent": intent,
            "payload": result.get("payload", {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _execute_document_pending(ctx: AgentContext, pending: dict) -> AgentResult:
    payload = pending.get("payload") or {}
    doc_type = str(payload.get("doc_type") or "other")
    entities = payload.get("entities") or {}
    actions = await DocumentService(ctx.db).dispatch(
        ctx.db, ctx.patient, doc_type, entities, None
    )
    effective = [a for a in actions if a.get("type") != "no_action"]
    if not effective:
        reply = "没有可归档的信息，本次未写入。"
    else:
        reply = "已按确认结果归档，可在健康档案和用药页查看。"
    return make_result(
        "document",
        reply=reply,
        actions=actions,
        payload={"doc_type": doc_type},
        presentation=build_presentation(
            "document",
            reply,
            summary="已归档病历信息" if effective else "没有可归档信息",
            key_points=[a.get("summary", "") for a in effective[:3]] or ["未写入任何记录"],
            action_items=["到健康档案核对诊断", "到用药页核对提醒"],
        ),
    )


async def _execute_medication_intake(ctx: AgentContext, pending: dict) -> AgentResult:
    """确认「已服药」→ 写 MedicationLog（不是提醒）。"""
    meds = (pending.get("payload") or {}).get("medications") or []
    actions: list[Action] = []
    names: list[str] = []
    errors: list[str] = []
    today = date.today()
    hhmm = datetime.now().strftime("%H:%M")
    for med in meds:
        name = med.get("medication_name") or med.get("name") or med.get("generic_name")
        if not name:
            continue
        try:
            log = MedicationLog(
                patient_id=ctx.patient.id,
                reminder_id=None,
                medication_name=str(name),
                local_date=today,
                time_of_day=hhmm,
                status="taken",
                reason="chat_intake",
            )
            ctx.db.add(log)
            await ctx.db.flush()
            names.append(str(name))
            actions.append(
                {
                    "type": "record_created",
                    "record_id": log.id,
                    "summary": f"已记录服药：{name}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    if not actions:
        return make_result(
            "medication", status="error",
            reply="记录服药失败，请稍后重试或手动打卡。",
            payload={"errors": errors},
        )
    actions.append({"type": "navigate", "target": "/medication", "summary": "查看用药"})
    reply = f"已记下您吃了 {'、'.join(names)}，今天的服药记录已更新。"
    if errors:
        reply += "部分药品未能记录，请手动核对。"
    return make_result(
        "medication",
        reply=reply,
        actions=actions,
        payload={"errors": errors, "logged": names},
        presentation=build_presentation(
            "medication", reply,
            summary="已记录服药",
            key_points=[f"已记录：{'、'.join(names)}", "今天的服药记录已更新"],
            action_items=["按医嘱继续服药", "有不适及时就医"],
        ),
    )


async def _execute_medication_pending(ctx: AgentContext, pending: dict) -> AgentResult:
    mode = (pending.get("payload") or {}).get("mode", "reminder")
    if mode == "intake":
        return await _execute_medication_intake(ctx, pending)
    meds = (pending.get("payload") or {}).get("medications") or []
    actions: list[Action] = []
    errors: list[str] = []
    for med in meds:
        name = med.get("medication_name") or med.get("name") or med.get("generic_name")
        if not name:
            continue
        try:
            reminder = await ReminderService(ctx.db).create(
                ctx.patient.id,
                MedicationReminderCreate(
                    medication_name=str(name),
                    brand_name=med.get("brand_name"),
                    spec=med.get("spec"),
                    dose=med.get("dose"),
                    dose_unit=med.get("dose_unit"),
                    frequency=str(med.get("frequency") or "qd"),
                    route=med.get("route"),
                    timing_note=med.get("timing_note"),
                    notes=med.get("notes"),
                ),
            )
            actions.append(
                {
                    "type": "reminder_created",
                    "reminder_id": reminder.id,
                    "summary": f"已添加用药提醒：{name}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    if not actions:
        return make_result(
            "medication", status="error",
            reply="添加用药失败，请稍后重试。",
            payload={"errors": errors},
        )
    actions.append({"type": "navigate", "target": "/medication", "summary": "查看用药"})
    reply = "已为您添加用药提醒，可在「用药」页查看。"
    if errors:
        reply += "部分药品未能添加，请手动核对。"
    return make_result(
        "medication",
        reply=reply,
        actions=actions,
        payload={"errors": errors},
        presentation=build_presentation(
            "medication", reply,
            summary="已添加用药提醒",
            key_points=["提醒已保存到用药页", "按提醒时间服药"],
            action_items=["到「用药」页核对药名和频次", "有不适及时就医"],
        ),
    )


async def execute_pending(ctx: AgentContext, pending: dict) -> AgentResult:
    """执行已确认的写库动作（阶段 1：monitor 指标；阶段 2：medication 提醒）。"""
    agent = pending.get("agent", "monitor")
    payload = pending.get("payload") or {}

    if agent == "medication":
        return await _execute_medication_pending(ctx, pending)
    if agent == "document":
        return await _execute_document_pending(ctx, pending)
    if agent != "monitor":
        return make_result(
            agent, status="error", reply="该操作暂不支持，请重新操作。"
        )

    metrics = payload.get("metrics") or []
    actions: list[Action] = []
    errors: list[str] = []
    for metric in metrics:
        try:
            record_type = metric.get("record_type")
            if record_type not in VALID_RECORD_TYPES:
                continue
            value = metric.get("value")
            if value is None:
                continue
            extra: dict[str, Any] = {}
            if record_type == "blood_pressure":
                extra["systolic"] = metric.get("systolic")
                extra["diastolic"] = metric.get("diastolic")
                value = metric.get("systolic") or value
            elif metric.get("context"):
                extra["type"] = metric["context"]

            record = await HealthService(ctx.db).create_record(
                ctx.patient,
                HealthRecordCreate(
                    record_type=RecordType(record_type),
                    value=float(value),
                    unit=str(metric.get("unit") or ""),
                    extra_data=extra,
                ),
            )
            await AlertService(ctx.db).evaluate_record(ctx.patient, record)
            actions.append(
                {
                    "type": "record_created",
                    "record_id": record.id,
                    "summary": f"已记录 {metric.get('name') or record_type} {value}{metric.get('unit') or ''}",
                }
            )
        except Exception as exc:  # noqa: BLE001 - 单条失败不影响其余指标
            errors.append(str(exc))

    if not actions:
        return make_result(
            "monitor", status="error",
            reply="记录失败，请稍后重试或手动录入。",
            payload={"errors": errors},
        )
    reply = "已经帮您记好了。"
    if errors:
        reply += "部分指标未能记录，请手动核对。"
    return make_result(
        "monitor",
        reply=reply,
        actions=actions,
        payload={"errors": errors},
        presentation=build_presentation(
            "monitor", reply,
            summary="已记录指标",
            key_points=[a.get("summary", "") for a in actions[:3]],
            action_items=["继续按计划监测", "有异常及时就医"],
        ),
    )


async def resume_pending(
    ctx: AgentContext, message: str, pending: dict
) -> AgentResult | None:
    kind = pending.get("kind")
    agent = pending.get("agent") or "monitor"

    if kind == "confirm_write":
        if is_confirm(message):
            result = await execute_pending(ctx, pending)
            await PendingStore.clear(ctx.patient.id, ctx.session_id)
            return result
        if is_cancel(message):
            await PendingStore.clear(ctx.patient.id, ctx.session_id)
            start = time.time()
            await ctx.log_trace(
                agent, "pending_cancelled", {"message": message[:200]},
                {"cancelled": True}, start,
            )
            return make_result(agent, reply="好的，已取消。")
        await PendingStore.clear(ctx.patient.id, ctx.session_id)
        return None

    if kind == "safety_120":
        if is_yes(message):
            await PendingStore.clear(ctx.patient.id, ctx.session_id)
            start = time.time()
            await ctx.log_trace(
                "safety", "120_confirmed", {"message": message[:200]},
                {"accepted": True}, start,
            )
            reply = "请立即拨打 120，或点右侧紧急呼叫。"
            return make_result(
                "safety",
                reply=reply,
                actions=[{"type": "safety_alert", "summary": "已提示拨打120"}],
                presentation=build_presentation(
                    "safety",
                    reply,
                    summary="请立即拨打 120",
                    key_points=["马上拨打 120", "让家人陪同，不要自行驾车"],
                    action_items=["立即拨打 120 或点右侧紧急呼叫"],
                    boundary="这是紧急情况，请立即就医。",
                    tts_text="请立即拨打 120，或点右侧紧急呼叫。",
                    emergency=True,
                ),
            )
        await PendingStore.clear(ctx.patient.id, ctx.session_id)
        start = time.time()
        await ctx.log_trace(
            "safety", "120_declined", {"message": message[:200]},
            {"declined": True}, start,
        )
        original = str(pending.get("original_message") or message)
        return await replay_skip_safety(ctx, original)

    return None


async def replay_skip_safety(ctx: AgentContext, original_message: str) -> AgentResult:
    """用户拒绝 120 后，用原消息重放 Router + Agent（跳过 Safety）。"""
    router = await router_agent(ctx, original_message)
    intent = str((router.get("payload") or {}).get("intent", "consult"))
    result = await dispatch_intent(ctx, intent, original_message)
    reply = result.get("reply", "")
    if reply and "如症状加重请立即就医" not in reply:
        result["reply"] = reply + "\n\n如症状加重请立即就医。"
    result["presentation"] = build_presentation(
        str(result.get("agent") or "consult"), str(result.get("reply") or "")
    )
    payload = dict(result.get("payload") or {})
    payload["intent"] = intent
    result["payload"] = payload
    return result


# ======================================================================
# 抽取接口（/agents/extract）
# ======================================================================


def _normalize_medication(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name") or raw.get("generic_name")
    if not name:
        return None
    out: dict[str, Any] = {
        "medication_name": str(name),
        "name": str(name),
        "frequency": str(raw.get("frequency") or "qd"),
    }
    for key in ("brand_name", "spec", "dose", "dose_unit", "route", "timing_note", "notes"):
        if raw.get(key) is not None:
            out[key] = raw[key]
    return out


async def extract_from_text(text: str) -> dict:
    """文本结构化抽取（只抽取、不写库；规格 §10.3）。"""
    metrics = await extract_metrics(text)
    if metrics:
        return {
            "kind": "metric",
            "metric": _metric_payload(metrics[0]),
            "metrics": [_metric_payload(m) for m in metrics],
        }

    meds = await extract_medications(text)
    if meds:
        return {"kind": "medication", "medication": meds[0], "medications": meds}

    return {"kind": "none", "metric": None, "medication": None, "metrics": [], "medications": []}


# ======================================================================
# 协调器入口
# ======================================================================


def _finalize(result: AgentResult, session_id: str, ctx: AgentContext, intent: str | None) -> dict[str, Any]:
    payload = result.get("payload") or {}
    return {
        "reply": result.get("reply", ""),
        "session_id": session_id,
        "intent": intent,
        "status": result.get("status", "ok"),
        "actions": result.get("actions", []),
        "evidence": result.get("evidence", []),
        "presentation": result.get("presentation"),
        "agent_traces": ctx.traces,
        "care_plan": payload.get("care_plan"),
        "followup": None,
    }


async def handle_message(
    db: AsyncSession, patient: Patient, message: str, session_id: str | None = None
) -> dict[str, Any]:
    """非流式唯一入口。"""
    is_new_session = not session_id
    session_id = session_id or str(uuid.uuid4())
    if is_new_session:
        # 会话结束触发记忆巩固：把上一会话的新事实写回患者画像（规格 §8）
        previous = await _latest_session_id(db, patient.id)
        if previous and previous != session_id:
            try:
                await MemoryService(db).consolidate(patient, previous)
            except Exception:
                pass
    history = await load_history(db, patient.id, session_id)
    ctx = AgentContext(db, patient, session_id, history=history)

    await save_message(db, patient.id, session_id, "user", message)
    if is_new_session:
        await enforce_session_limit(db, patient.id)

    try:
        pending = await PendingStore.get(patient.id, session_id)
        if pending:
            resumed = await resume_pending(ctx, message, pending)
            if resumed is not None:
                intent = (resumed.get("payload") or {}).get("intent") or pending.get("original_intent")
                await _maybe_set_pending(ctx, resumed, intent, pending.get("original_message") or message)
                await save_message(db, patient.id, session_id, "assistant", resumed.get("reply", ""))
                await _save_context(patient, session_id, intent)
                return _finalize(resumed, session_id, ctx, intent)

        # 规格 §6：Safety 为全局前置（病历也先过 Safety）
        safety = await safety_agent(ctx, message)
        if safety.get("status") == "blocked":
            await PendingStore.set(
                patient.id,
                session_id,
                {
                    "kind": "safety_120",
                    "agent": "safety",
                    "original_message": message,
                    "original_intent": None,
                    "payload": safety.get("payload", {}),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await save_message(db, patient.id, session_id, "assistant", safety.get("reply", ""))
            await _save_context(patient, session_id, None)
            return _finalize(safety, session_id, ctx, None)

        router = await router_agent(ctx, message)
        intent = str((router.get("payload") or {}).get("intent", "consult"))
        result = await dispatch_intent(ctx, intent, message)
        await _maybe_set_pending(ctx, result, intent, message)
        await save_message(db, patient.id, session_id, "assistant", result.get("reply", ""))
        await _save_context(patient, session_id, intent)
        return _finalize(result, session_id, ctx, intent)
    except Exception as exc:  # noqa: BLE001 - 兜底成友好错误
        try:
            await ctx.log_trace(
                "orchestrator", "handle_error", {"message": message[:200]},
                {}, time.time(), status="error", error=str(exc),
            )
        except Exception:
            pass
        try:
            await db.rollback()
        except Exception:
            pass
        error_result = make_result(
            "orchestrator", status="error",
            reply="服务暂时不可用，请稍后重试。",
        )
        return _finalize(error_result, session_id, ctx, None)


async def _emit_result(result: AgentResult):
    for action in result.get("actions", []):
        yield {"type": "action", "data": action}
    for evidence in result.get("evidence", []):
        yield {"type": "evidence", "data": evidence}


def _done_event(result: AgentResult, session_id: str, intent: str | None) -> dict[str, Any]:
    payload = result.get("payload") or {}
    return {
        "type": "done",
        "session_id": session_id,
        "intent": intent,
        "status": result.get("status", "ok"),
        "actions": result.get("actions", []),
        "evidence": result.get("evidence", []),
        "presentation": result.get("presentation"),
        "care_plan": payload.get("care_plan"),
        "followup": None,
    }


async def handle_stream(
    db: AsyncSession, patient: Patient, message: str, session_id: str | None = None
):
    """流式唯一入口：token / trace / action / evidence / done / error。"""
    is_new_session = not session_id
    session_id = session_id or str(uuid.uuid4())
    if is_new_session:
        # 会话结束触发记忆巩固：把上一会话的新事实写回患者画像（规格 §8）
        previous = await _latest_session_id(db, patient.id)
        if previous and previous != session_id:
            try:
                await MemoryService(db).consolidate(patient, previous)
            except Exception:
                pass
    history = await load_history(db, patient.id, session_id)
    ctx = AgentContext(db, patient, session_id, history=history)

    await save_message(db, patient.id, session_id, "user", message)
    if is_new_session:
        await enforce_session_limit(db, patient.id)
    try:
        await db.commit()
    except Exception:
        pass

    emitted = 0

    try:
        pending = await PendingStore.get(patient.id, session_id)
        if pending:
            result = await resume_pending(ctx, message, pending)
            if result is not None:
                for trace in ctx.traces[emitted:]:
                    yield {"type": "trace", "data": trace}
                emitted = len(ctx.traces)
                intent = (result.get("payload") or {}).get("intent") or pending.get("original_intent")
                await _maybe_set_pending(ctx, result, intent, pending.get("original_message") or message)
                await save_message(db, patient.id, session_id, "assistant", result.get("reply", ""))
                await db.commit()
                await _save_context(patient, session_id, intent)
                yield {"type": "token", "data": result.get("reply", "")}
                async for event in _emit_result(result):
                    yield event
                yield _done_event(result, session_id, intent)
                return

        safety = await safety_agent(ctx, message)
        for trace in ctx.traces[emitted:]:
            yield {"type": "trace", "data": trace}
        emitted = len(ctx.traces)

        if safety.get("status") == "blocked":
            await PendingStore.set(
                patient.id,
                session_id,
                {
                    "kind": "safety_120",
                    "agent": "safety",
                    "original_message": message,
                    "original_intent": None,
                    "payload": safety.get("payload", {}),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await save_message(db, patient.id, session_id, "assistant", safety.get("reply", ""))
            await db.commit()
            await _save_context(patient, session_id, None)
            yield {"type": "token", "data": safety.get("reply", "")}
            async for event in _emit_result(safety):
                yield event
            yield _done_event(safety, session_id, None)
            return

        router = await router_agent(ctx, message)
        for trace in ctx.traces[emitted:]:
            yield {"type": "trace", "data": trace}
        emitted = len(ctx.traces)
        intent = str((router.get("payload") or {}).get("intent", "consult"))

        if intent == "consult":
            messages, evidence = await build_consult_messages(ctx, message)
            parts: list[str] = []
            start = time.time()
            async for token in llm_service.chat_stream(messages):
                parts.append(token)
                yield {"type": "token", "data": token}
            streamed = "".join(parts)
            reply = ensure_disclaimer(streamed)
            if reply != streamed:
                yield {"type": "token", "data": reply[len(streamed):]}
            await ctx.log_trace(
                "consult", "symptom_consultation", {"message": message[:200]},
                {"reply": reply[:300]}, start,
                evidence=evidence, fallback=not llm_service.is_available,
            )
            yield {"type": "trace", "data": ctx.traces[-1]}
            emitted = len(ctx.traces)
            result = make_result("consult", reply=reply, evidence=evidence)
            if any(k in message for k in SYMPTOM_KEYS):
                plan = await planner_agent(ctx, "根据当前症状调整管理方案")
                for trace in ctx.traces[emitted:]:
                    yield {"type": "trace", "data": trace}
                emitted = len(ctx.traces)
                result["actions"] = plan.get("actions", [])
                result["evidence"] = list(result.get("evidence", [])) + list(plan.get("evidence", []))
                result["payload"] = {"care_plan": (plan.get("payload") or {}).get("care_plan")}
        elif intent == "planner":
            result = await planner_agent(ctx, message)
            for trace in ctx.traces[emitted:]:
                yield {"type": "trace", "data": trace}
            emitted = len(ctx.traces)
            yield {"type": "token", "data": result.get("reply", "")}
        else:
            result = await dispatch_intent(ctx, intent, message)
            for trace in ctx.traces[emitted:]:
                yield {"type": "trace", "data": trace}
            emitted = len(ctx.traces)
            yield {"type": "token", "data": result.get("reply", "")}

        await _maybe_set_pending(ctx, result, intent, message)
        await save_message(db, patient.id, session_id, "assistant", result.get("reply", ""))
        await db.commit()
        await _save_context(patient, session_id, intent)

        async for event in _emit_result(result):
            yield event
        yield _done_event(result, session_id, intent)

    except Exception as exc:  # noqa: BLE001
        try:
            await ctx.log_trace(
                "orchestrator", "stream_error", {}, {"error": str(exc)},
                time.time(), status="error", error=str(exc),
            )
        except Exception:
            pass
        try:
            await db.rollback()
        except Exception:
            pass
        yield {"type": "error", "message": "服务暂时不可用，请稍后重试"}
        yield {
            "type": "done",
            "session_id": session_id,
            "intent": None,
            "status": "error",
            "actions": [],
            "evidence": [],
            "care_plan": None,
            "followup": None,
        }
