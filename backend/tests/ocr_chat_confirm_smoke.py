"""聊天粘贴病历：先确认后归档，且回复不贴原文（OCR 规格 §一 / §六）。"""

import json
import os

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8080/api")
client = httpx.Client(timeout=180)
login = client.post(f"{BASE}/auth/login", json={"email": "demo@nurse.com", "password": "demo123"})
login.raise_for_status()
H = {"Authorization": f"Bearer {login.json()['access_token']}"}

record = (
    "门诊病历（测试样例）：患者反复头晕3天，伴乏力。"
    "既往史：2型糖尿病5年，高血压3年，规律服用二甲双胍、氨氯地平；否认药物过敏史。"
    "辅助检查：空腹血糖7.8mmol/L，糖化血红蛋白7.5%。"
    "诊断：2型糖尿病；高血压2级。"
    "治疗方案：调整降压方案，继续口服降糖药，低盐低脂饮食，2周后复诊。"
    "就诊日期：2026-10-06。"
)

r = client.post(f"{BASE}/agents/chat", json={"message": record}, headers=H)
r.raise_for_status()
data = r.json()
print("status=", data.get("status"), "intent=", data.get("intent"))
print("reply_has_raw=", "门诊病历（测试样例）" in data.get("reply", ""))
print("reply_has_confirm=", "确认" in data.get("reply", ""))
print("reply_prefix=", data.get("reply", "")[:120])

if data.get("status") == "needs_confirmation":
    c = client.post(
        f"{BASE}/agents/chat",
        json={"message": "确认", "session_id": data["session_id"]},
        headers=H,
    )
    c.raise_for_status()
    confirmed = c.json()
    print("confirm_status=", confirmed.get("status"))
    print("confirm_actions=", json.dumps(confirmed.get("actions", []), ensure_ascii=False))
    print("diagnoses=", json.dumps(client.get(f"{BASE}/diagnoses", headers=H).json(), ensure_ascii=False))
    print("appointments=", json.dumps(client.get(f"{BASE}/appointments", headers=H).json(), ensure_ascii=False))
