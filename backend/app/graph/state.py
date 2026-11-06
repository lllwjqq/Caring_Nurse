"""Agent 输出契约与待确认状态存储（规格 §4 / §7）。

- AgentResult：所有 agent 的唯一返回结构，禁止裸 dict。
- PendingStore：confirm_write / safety_120 / diagnosis_session 外置状态（Redis）。
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.graph.presentation import build_presentation
from app.services.redis_client import redis_client


class Action(TypedDict, total=False):
    type: str
    record_id: int
    reminder_id: int
    diagnosis_id: int
    appointment_id: int
    target: str
    level: str
    message: str
    summary: str


class Evidence(TypedDict, total=False):
    source: str
    title: str
    snippet: str
    relation: str
    score: float


class Presentation(TypedDict, total=False):
    summary: str
    key_points: list[str]
    action_items: list[str]
    boundary: str
    tts_text: str


class AgentResult(TypedDict, total=False):
    agent: str
    status: Literal["ok", "needs_confirmation", "blocked", "error"]
    reply: str
    payload: dict
    actions: list[Action]
    evidence: list[Evidence]
    presentation: Presentation
    trace: dict


def make_result(
    agent: str,
    status: str = "ok",
    reply: str = "",
    payload: dict | None = None,
    actions: list[Action] | None = None,
    evidence: list[Evidence] | None = None,
    presentation: Presentation | None = None,
    trace: dict | None = None,
) -> AgentResult:
    """统一构造 AgentResult，保证字段齐全；有 reply 时自动补 presentation。"""
    if presentation is None and reply:
        presentation = build_presentation(  # type: ignore[assignment]
            agent, reply, emergency=(status == "blocked")
        )
    result: AgentResult = {
        "agent": agent,
        "status": status,  # type: ignore[typeddict-item]
        "reply": reply,
        "payload": payload or {},
        "actions": actions or [],
        "evidence": evidence or [],
        "trace": trace or {},
    }
    if presentation:
        result["presentation"] = presentation
    return result


PENDING_TTL = 600


class PendingStore:
    """Redis 外置会话状态：pending:{patient_id}:{session_id}，TTL 600s。"""

    @staticmethod
    def _key(patient_id: int, session_id: str) -> str:
        return f"pending:{patient_id}:{session_id}"

    @staticmethod
    async def get(patient_id: int, session_id: str) -> dict | None:
        try:
            data = await redis_client.get_json(PendingStore._key(patient_id, session_id))
            return data if isinstance(data, dict) else None
        except Exception:
            # Redis 不可用 → 视为无 pending（规格 §12）
            return None

    @staticmethod
    async def set(
        patient_id: int, session_id: str, data: dict, ttl: int = PENDING_TTL
    ) -> None:
        try:
            await redis_client.set_json(
                PendingStore._key(patient_id, session_id), data, expire=ttl
            )
        except Exception:
            # pending 写入失败不阻塞主流程
            pass

    @staticmethod
    async def clear(patient_id: int, session_id: str) -> None:
        try:
            await redis_client.delete(PendingStore._key(patient_id, session_id))
        except Exception:
            pass


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def empty_payload() -> dict[str, Any]:
    return {}
