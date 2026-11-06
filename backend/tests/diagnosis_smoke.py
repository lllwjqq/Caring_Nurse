"""阶段 3 诊断 Agent 冒烟测试（规格 §5.8 / §9）。

运行：在 backend 目录执行 `python tests/diagnosis_smoke.py`
"""

import os

import httpx

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


# 1) 症状 → 可能方向 + 依据 + 免责声明
s = chat("我最近头晕头痛、乏力，可能是什么病")
reply = s.get("reply", "")
check("diagnosis_intent", s.get("intent") == "diagnosis", f"intent={s.get('intent')}")
check("diagnosis_status", s.get("status") == "ok", f"status={s.get('status')}")
check("has_possible_direction", "可能方向" in reply and "高血压" in reply)
check("has_evidence", bool(s.get("evidence")), f"evidence={len(s.get('evidence') or [])}")
check("has_disclaimer", "免责声明" in reply)

traces = client.get(f"{BASE}/agents/traces/{s['session_id']}", headers=H).json()
agents = [t.get("agent_name") for t in traces]
check("diagnosis_trace", "diagnosis" in agents, f"agents={agents}")

# 2) 信息不足 → 不硬下结论
u = chat("我可能是什么病")
check(
    "insufficient_info",
    u.get("intent") == "diagnosis" and "请先描述" in u.get("reply", ""),
    f"intent={u.get('intent')}",
)

# 3) Safety-first：诊断请求也必须先经过 Safety（是否拦截由 LLM 复核决定）
r = chat("胸痛可能是什么病")
traces_r = client.get(f"{BASE}/agents/traces/{r['session_id']}", headers=H).json()
agents_r = [t.get("agent_name") for t in traces_r]
check(
    "safety_first_diagnosis",
    bool(agents_r) and agents_r[0] == "safety",
    f"agents={agents_r} status={r.get('status')}",
)
if r.get("status") == "blocked":
    chat("不用", r["session_id"])

print("OVERALL", "PASS" if ok else "FAIL")
