import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings


class RedisClient:
    def __init__(self):
        self._client: aioredis.Redis | None = None

    async def connect(self):
        self._client = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def disconnect(self):
        if self._client:
            await self._client.close()

    @property
    def client(self) -> aioredis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected")
        return self._client

    async def set_json(self, key: str, value: Any, expire: int | None = None):
        await self.client.set(key, json.dumps(value, ensure_ascii=False), ex=expire)

    async def get_json(self, key: str) -> Any | None:
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def blacklist_token(self, token: str, expire_seconds: int):
        await self.client.set(f"blacklist:{token}", "1", ex=expire_seconds)

    async def is_token_blacklisted(self, token: str) -> bool:
        return bool(await self.client.get(f"blacklist:{token}"))

    async def publish_alert(self, patient_id: int, alert_data: dict):
        await self.client.publish(f"alerts:{patient_id}", json.dumps(alert_data, ensure_ascii=False))

    async def push_alert_stream(self, alert_data: dict):
        await self.client.xadd("alert_stream", {"data": json.dumps(alert_data, ensure_ascii=False)})

    async def set_patient_context(self, patient_id: int, context: dict, expire: int = 3600):
        await self.set_json(f"patient_context:{patient_id}", context, expire=expire)

    async def get_patient_context(self, patient_id: int) -> dict | None:
        return await self.get_json(f"patient_context:{patient_id}")


redis_client = RedisClient()
