"""记忆巩固 + GSSC 上下文冒烟测试（规格 §8 / §9）。

运行：在 backend 目录执行 `python tests/memory_smoke.py`
前置：后端已运行；演示账号 demo@nurse.com / demo123。
测试后会把 allergies 恢复为「青霉素」。
"""

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8080/api")
client = httpx.Client(timeout=120)

login = client.post(f"{BASE}/auth/login", json={"email": "demo@nurse.com", "password": "demo123"})
login.raise_for_status()
TOKEN = login.json()["access_token"]
H = {"Authorization": f"Bearer {TOKEN}"}

ok = True


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    print(("PASS" if cond else "FAIL"), name, extra)


def chat(message: str, session_id: str | None = None) -> dict:
    body: dict = {"message": message}
    if session_id:
        body["session_id"] = session_id
    resp = client.post(f"{BASE}/agents/chat", json=body, headers=H)
    resp.raise_for_status()
    return resp.json()


# ---- GSSC 上下文超预算压缩 ----
from app.graph.context_builder import build_context_messages  # noqa: E402

messages = build_context_messages(
    role="你是测试助手",
    patient_context="患者信息" * 3000,
    evidence=[{"source": "指南", "title": "条目", "snippet": "内容" * 200}],
    history=[{"role": "user", "content": "历史" * 300} for _ in range(20)],
    task="请回答",
    output_hint="输出建议",
    max_tokens=500,
)
check(
    "context_budget_compress",
    "内容已压缩" in messages[0]["content"],
    f"system_len={len(messages[0]['content'])} history={len(messages) - 2}",
)

# ---- 记忆巩固：先说新过敏，再开新会话触发巩固 ----
s1 = chat("我最近对磺胺过敏")
check("allergy_message_ok", s1.get("status") in ("ok", "blocked"), f"status={s1.get('status')}")

s2 = chat("你好")  # 新会话 → 巩固上一会话
check("new_session_ok", s2.get("status") == "ok", f"status={s2.get('status')}")

profile = client.get(f"{BASE}/patients/me", headers=H).json()
allergies = profile.get("allergies") or ""
check("consolidated_allergy", "磺胺" in allergies, f"allergies={allergies}")

# 恢复演示数据
client.put(f"{BASE}/patients/me", json={"allergies": "青霉素"}, headers=H)

print("OVERALL", "PASS" if ok else "FAIL")
