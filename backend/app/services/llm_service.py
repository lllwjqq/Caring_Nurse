import hashlib
import json
from typing import AsyncGenerator

import httpx
import numpy as np

from app.config import settings


class LLMService:
    DISCLAIMER = "【免责声明】以下建议仅供参考，不能替代专业医疗诊断，请遵医嘱。"

    def __init__(self):
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        if not self.is_available:
            return self._mock_response(messages)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "messages": messages, "temperature": temperature},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return self._mock_response(messages)

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        if not self.is_available:
            text = self._mock_response(messages)
            for chunk in [text[i : i + 20] for i in range(0, len(text), 20)]:
                yield chunk
            return
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data = json.loads(line[6:])
                        delta = data["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta

    async def embed(self, text: str) -> list[float]:
        if not self.is_available:
            return self._mock_embedding(text)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": settings.llm_embedding_model, "input": text},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except Exception:
            return self._mock_embedding(text)

    def _mock_embedding(self, text: str, dim: int = 384) -> list[float]:
        h = hashlib.md5(text.encode()).hexdigest()
        rng = np.random.RandomState(int(h[:8], 16))
        vec = rng.randn(dim).tolist()
        norm = np.linalg.norm(vec)
        return [v / norm for v in vec]

    def _mock_response(self, messages: list[dict]) -> str:
        last = messages[-1]["content"] if messages else ""
        if "方案" in last or "计划" in last:
            return (
                f"{self.DISCLAIMER}\n\n"
                "根据您的健康档案，建议：\n"
                "1. 饮食：低盐低脂，每日蔬菜500g，控制精制碳水\n"
                "2. 运动：每周至少150分钟中等强度有氧运动\n"
                "3. 监测：每日监测血压/血糖，记录异常值\n"
                "4. 用药：请严格遵医嘱，不可自行调整剂量"
            )
        if "头晕" in last or "不舒服" in last or "症状" in last:
            return (
                f"{self.DISCLAIMER}\n\n"
                "头晕可能与血压波动、血糖异常或睡眠不足有关。建议您：\n"
                "1. 立即测量当前血压和血糖\n"
                "2. 保持休息，避免突然起立\n"
                "3. 如症状持续或加重，请及时就医\n"
                "参考：《中国高血压防治指南》建议高血压患者应规律监测血压。"
            )
        return (
            f"{self.DISCLAIMER}\n\n"
            "我是您的贴心小护士，可以帮您解答慢病管理相关问题，"
            "包括饮食、运动、用药和日常监测建议。请告诉我您的具体需求。"
        )


llm_service = LLMService()
