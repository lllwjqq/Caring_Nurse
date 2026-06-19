from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Patient
from app.services.redis_client import redis_client

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/alerts/{patient_id}")
async def alert_websocket(websocket: WebSocket, patient_id: int):
    await websocket.accept()
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
