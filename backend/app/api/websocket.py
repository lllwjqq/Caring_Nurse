"""预警实时推送 WebSocket（规格附录 A.4：token 鉴权）。"""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Patient
from app.services.redis_client import redis_client

router = APIRouter(tags=["WebSocket"])


async def _authorize_patient(patient_id: int, token: str | None) -> bool:
    """校验 access token，并确认该 patient 属于 token 对应的用户。"""
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return False
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        return False

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Patient).where(Patient.user_id == user_id))
        patient = result.scalar_one_or_none()
        return patient is not None and patient.id == patient_id


@router.websocket("/ws/alerts/{patient_id}")
async def alert_websocket(
    websocket: WebSocket,
    patient_id: int,
    token: str | None = Query(default=None),
):
    await websocket.accept()
    if not await _authorize_patient(patient_id, token):
        # 鉴权失败：accept 后以 4401 关闭，前端据此停止重连
        await websocket.close(code=4401)
        return

    pubsub = redis_client.client.pubsub()
    channel = f"alerts:{patient_id}"
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text('{"type":"pong"}')
            except Exception:
                pass
    except WebSocketDisconnect:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
