"""阶段 1 Agent 层冒烟测试（真实后端，UTF-8）。

运行：在 backend 目录执行 `python tests/stage1_smoke.py`
需要后端已在 localhost:8080 运行，演示账号 demo@nurse.com / demo123。
"""

import json
import os

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8080/api")
client = httpx.Client(timeout=120)

login = client.post(f"{BASE}/auth/login", json={"email": "demo@nurse.com", "password": "demo123"})
login.raise_for_status()
TOKEN = login.json()["access_token"]
H = {"Authorization": f"Bearer {TOKEN}"}

ok = True
record_ids: list[int] = []


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


# 1) Safety 拦截 + 拒绝后继续
s = chat("我胸口疼得厉害")
check("safety_blocked", s.get("status") == "blocked", f"status={s.get('status')} intent={s.get('intent')}")
check("safety_asks_120", "120" in s.get("reply", ""))
sid = s["session_id"]
s2 = chat("不用", sid)
check(
    "decline_continues",
    s2.get("status") == "ok" and "如症状加重" in s2.get("reply", ""),
    f"status={s2.get('status')} intent={s2.get('intent')}",
)
traces_s = client.get(f"{BASE}/agents/traces/{sid}", headers=H).json()
check(
    "decline_logged",
    any(t.get("action") == "120_declined" for t in traces_s),
    f"actions={[t.get('action') for t in traces_s]}",
)

# 1c) 同意拨打 120 → safety_alert action
sy = chat("我胸口疼得厉害")
sy2 = chat("要", sy["session_id"])
check(
    "safety_accept_120",
    sy2.get("status") == "ok"
    and any(a.get("type") == "safety_alert" for a in (sy2.get("actions") or [])),
    f"status={sy2.get('status')} actions={[a.get('type') for a in (sy2.get('actions') or [])]}",
)

# 1d) 待确认时发无关消息 → 清 pending 并正常路由
u = chat("我早上空腹血糖7.1")
u2 = chat("今天天气怎么样", u["session_id"])
check(
    "pending_cleared_on_unrelated",
    u2.get("status") == "ok" and not (u2.get("actions") or []),
    f"status={u2.get('status')} intent={u2.get('intent')}",
)

# 2) Monitor 抽取 → 确认入库
m = chat("我早上空腹血糖6.8")
check(
    "monitor_needs_confirm",
    m.get("status") == "needs_confirmation" and m.get("intent") == "monitor",
    f"status={m.get('status')} intent={m.get('intent')}",
)
check("monitor_reply_desc", "空腹血糖 6.8" in m.get("reply", ""))
msid = m["session_id"]
m2 = chat("确认", msid)
acts = m2.get("actions") or []
record_ids.extend(a.get("record_id") for a in acts if a.get("type") == "record_created" and a.get("record_id"))
check(
    "confirm_writes",
    m2.get("status") == "ok" and any(a.get("type") == "record_created" for a in acts),
    f"status={m2.get('status')} actions={[a.get('type') for a in acts]}",
)

# 3) 取消不写库
c = chat("我餐后血糖11.2")
c2 = chat("取消", c["session_id"])
check("cancel_no_write", c2.get("status") == "ok" and "取消" in c2.get("reply", ""), f"status={c2.get('status')}")

# 4) 否定词不误报
n = chat("我没有胸痛，就是想问饮食")
check("negated_not_blocked", n.get("status") != "blocked", f"status={n.get('status')} intent={n.get('intent')}")

# 5) Planner 解析并落 CarePlan
p = chat("请为我制定管理方案")
check(
    "planner_care_plan",
    bool(p.get("care_plan")) and p.get("intent") == "planner",
    f"intent={p.get('intent')} care_plan={bool(p.get('care_plan'))}",
)

# 6) 旧字段保持
check(
    "old_fields",
    all(k in p for k in ("reply", "session_id", "agent_traces", "care_plan")),
)

# 7) /agents/extract 只抽取
e = client.post(f"{BASE}/agents/extract", json={"text": "空腹血糖6.8"}, headers=H).json()
check(
    "extract_metric",
    e.get("kind") == "metric" and (e.get("metric") or {}).get("extra_data", {}).get("type") == "fasting",
    f"kind={e.get('kind')} metric={json.dumps(e.get('metric'), ensure_ascii=False)}",
)

# 8) SSE 事件 + 确认后 action
with client.stream("POST", f"{BASE}/agents/chat/stream", json={"message": "我早上血压135/85"}, headers=H) as r:
    text = "".join(r.iter_text())
check(
    "stream_events",
    '"type": "trace"' in text and '"type": "token"' in text and '"type": "done"' in text and "needs_confirmation" in text,
)

# 8a) Consult SSE 带 evidence 事件
with client.stream("POST", f"{BASE}/agents/chat/stream", json={"message": "我头晕怎么办"}, headers=H) as r:
    text_consult = "".join(r.iter_text())
check("stream_evidence", '"type": "evidence"' in text_consult)
events = []
for line in text.splitlines():
    line = line.strip()
    if line.startswith("data: "):
        events.append(json.loads(line[6:]))
done = [x for x in events if x.get("type") == "done"][-1]
ssid = done["session_id"]

with client.stream("POST", f"{BASE}/agents/chat/stream", json={"message": "确认", "session_id": ssid}, headers=H) as r:
    text2 = "".join(r.iter_text())
check("stream_confirm_action", '"type": "action"' in text2 and '"status": "ok"' in text2)
for line in text2.splitlines():
    line = line.strip()
    if line.startswith("data: "):
        ev = json.loads(line[6:])
        if ev.get("type") == "action":
            rid = (ev.get("data") or {}).get("record_id")
            if rid:
                record_ids.append(rid)

# 9) 落库校验
recs = client.get(f"{BASE}/health/records", params={"days": 1}, headers=H).json()
has_glucose = any(
    r["record_type"] == "blood_glucose" and abs(float(r["value"]) - 6.8) < 0.01 for r in recs
)
check("record_persisted", has_glucose, f"records={len(recs)}")

# 10) trace 可观测字段
tr = client.get(f"{BASE}/agents/traces/{msid}", headers=H).json()
check(
    "trace_observability",
    bool(tr) and "status" in (tr[0].get("output_data") or {}),
    f"traces={len(tr)}",
)

# 清理测试写入的健康记录
for rid in record_ids:
    try:
        client.delete(f"{BASE}/health/records/{rid}", headers=H)
    except Exception:
        pass

print("OVERALL", "PASS" if ok else "FAIL")
