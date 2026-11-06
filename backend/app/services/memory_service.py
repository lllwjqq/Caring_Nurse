"""四层记忆与巩固/遗忘（规格 §8）。

- 工作记忆：Redis patient_context / PendingStore（orchestrator 已用）
- 情景记忆：AgentTrace + ChatMessage
- 语义记忆：Patient（allergies / medications / health_profile）
- 知识记忆：KnowledgeChunk（RAG）

巩固：从最近会话抽取「新且确定」的事实，写回患者画像；
     只写明确出现的事实，不确定的不写。
遗忘：会话上限已在 orchestrator；AgentTrace 清理默认关闭。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentTrace, ChatMessage, Patient
from app.services.llm_service import llm_service
from app.services.redis_client import redis_client

CONSOLIDATE_SYSTEM = (
    "你是患者健康档案整理助手。从最近对话中抽取「患者本人、明确说出」的新事实。\n"
    "只输出 JSON，不要其他文字：\n"
    '{"allergies":[],"medications":[],"symptoms":[],"habits":[]}\n'
    "规则：\n"
    "- 只抽取明确出现的内容，不确定的不要写；\n"
    "- allergies 只写药物/食物过敏原；\n"
    "- medications 只写药名；\n"
    "- symptoms 写持续症状；habits 写吸烟/饮酒/熬夜等。\n"
)


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in re.split(r"[、,，;；\s]+", value) if p.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_working_memory(self, patient_id: int) -> dict | None:
        try:
            return await redis_client.get_patient_context(patient_id)
        except Exception:
            return None

    async def set_working_memory(self, patient_id: int, context: dict) -> None:
        try:
            await redis_client.set_patient_context(patient_id, context)
        except Exception:
            pass

    async def consolidate(
        self, patient: Patient, session_id: str, *, trace_session_id: str | None = None
    ) -> dict:
        """把一个会话的新事实写回患者画像（幂等：同一会话只巩固一次）。"""
        marker = f"memory_consolidated:{patient.id}:{session_id}"
        try:
            if await redis_client.client.get(marker):
                return {"skipped": True}
        except Exception:
            pass

        result = await self.db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.patient_id == patient.id,
                ChatMessage.session_id == session_id,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(20)
        )
        messages = list(reversed(list(result.scalars().all())))
        if not messages:
            return {"skipped": True}

        text = "\n".join(f"{m.role}: {m.content}" for m in messages)
        facts = await self._extract_facts(text)
        changed: dict[str, Any] = {}

        existing_allergies = _split_list(patient.allergies)
        new_allergies = [a for a in facts.get("allergies", []) if a not in existing_allergies]
        if new_allergies:
            patient.allergies = "、".join(existing_allergies + new_allergies)
            changed["allergies"] = new_allergies

        existing_meds = _split_list(patient.medications)
        new_meds = [m for m in facts.get("medications", []) if m not in existing_meds]
        if new_meds:
            patient.medications = "、".join(existing_meds + new_meds)
            changed["medications"] = new_meds

        profile = dict(patient.health_profile or {})
        for field in ("symptoms", "habits"):
            existing = [str(x) for x in (profile.get(field) or [])]
            new_values = [x for x in facts.get(field, []) if x not in existing]
            if new_values:
                profile[field] = existing + new_values
                changed[field] = new_values
        profile["last_consolidated_at"] = datetime.now(timezone.utc).isoformat()
        patient.health_profile = profile

        self.db.add(
            AgentTrace(
                patient_id=patient.id,
                session_id=trace_session_id or session_id,
                agent_name="memory",
                action="memory_consolidate",
                input_data={"session_id": session_id},
                output_data={"facts": facts, "changed": changed},
                duration_ms=0,
            )
        )
        await self.db.flush()

        try:
            await redis_client.client.set(marker, "1", ex=7 * 24 * 3600)
        except Exception:
            pass
        return {"facts": facts, "changed": changed}

    async def consolidate_inactive(self, idle_minutes: int = 30) -> int:
        """扫描 30 分钟无活动的会话并巩固（供 APScheduler 调用）。"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=idle_minutes)
        result = await self.db.execute(
            select(ChatMessage.patient_id, ChatMessage.session_id)
            .group_by(ChatMessage.patient_id, ChatMessage.session_id)
            .having(func.max(ChatMessage.created_at) < cutoff)
        )
        count = 0
        for patient_id, session_id in result.all():
            patient = await self.db.get(Patient, patient_id)
            if not patient:
                continue
            outcome = await self.consolidate(patient, session_id)
            if not outcome.get("skipped"):
                count += 1
        return count

    async def forget_old_traces(self, days: int = 90, enabled: bool = False) -> int:
        """遗忘：按时间清理低价值 trace；默认关闭（规格 §8）。"""
        if not enabled:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(delete(AgentTrace).where(AgentTrace.created_at < cutoff))
        await self.db.flush()
        return int(result.rowcount or 0)

    async def _extract_facts(self, text: str) -> dict[str, list[str]]:
        if llm_service.is_available:
            try:
                result = await llm_service.extract_json(CONSOLIDATE_SYSTEM, text)
                if isinstance(result, dict):
                    normalized = self._normalize_facts(result)
                    if any(normalized.values()):
                        return normalized
            except Exception:
                pass
        return self._rule_facts(text)

    @staticmethod
    def _normalize_facts(data: dict) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for key in ("allergies", "medications", "symptoms", "habits"):
            value = data.get(key)
            if isinstance(value, list):
                out[key] = _dedupe([str(v) for v in value])
            elif isinstance(value, str) and value.strip():
                out[key] = [value.strip()]
            else:
                out[key] = []
        return out

    @staticmethod
    def _rule_facts(text: str) -> dict[str, list[str]]:
        allergies: list[str] = []
        for match in re.finditer(r"([\u4e00-\u9fa5]{2,12})过敏", text):
            window = text[max(0, match.start() - 6):match.start()]
            if any(word in window for word in ("没有", "不", "无", "没")):
                continue
            term = re.sub(r"^(?:我|对|最近|现在|以前)+", "", match.group(1))
            if len(term) >= 2:
                allergies.append(term)

        medications = [
            match.group(1)
            for match in re.finditer(
                r"(?:吃|服用|加了?)([\u4e00-\u9fa5A-Za-z0-9]{2,20}?(?:片|胶囊|颗粒|丸|注射液|口服液|软膏|滴眼液|喷雾|贴剂|散))",
                text,
            )
        ]
        symptoms = re.findall(r"(头晕|头痛|胸闷|气短|乏力|口干|多饮|多尿|心悸|水肿|咳嗽)", text)
        habits = re.findall(r"(抽烟|吸烟|喝酒|饮酒|熬夜|失眠)", text)

        return {
            "allergies": _dedupe(allergies),
            "medications": _dedupe(medications),
            "symptoms": _dedupe(symptoms),
            "habits": _dedupe(habits),
        }
