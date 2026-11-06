"""阶段 2 用药安全冒烟测试（真实后端，UTF-8）。

运行：在 backend 目录执行 `python tests/stage2_smoke.py`
需要后端已在 localhost:8080 运行，演示账号 demo@nurse.com / demo123。
测试结束会删除本次创建的提醒。
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
created_reminders: list[int] = []


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


def safety() -> list[dict]:
    resp = client.get(f"{BASE}/medication/safety", headers=H)
    resp.raise_for_status()
    return resp.json().get("issues", [])


def collect_reminders(result: dict) -> None:
    for action in result.get("actions") or []:
        if action.get("type") == "reminder_created" and action.get("reminder_id"):
            created_reminders.append(action["reminder_id"])


try:
    baseline = safety()
    print("baseline safety issues:", len(baseline))

    # 1) 过敏冲突：演示患者青霉素过敏 + 阿莫西林
    s = chat("帮我加阿莫西林100mg每天一次")
    check(
        "med_needs_confirm",
        s.get("status") == "needs_confirmation" and s.get("intent") == "medication",
        f"status={s.get('status')} intent={s.get('intent')}",
    )
    check("allergy_warned", "过敏" in s.get("reply", ""))
    s2 = chat("确认", s["session_id"])
    collect_reminders(s2)
    check(
        "allergy_reminder_created",
        any(a.get("type") == "reminder_created" for a in (s2.get("actions") or [])),
    )
    issues = safety()
    check(
        "safety_endpoint_allergy",
        any(i.get("level") == "red" and "阿莫西林" in i.get("title", "") for i in issues),
        f"issues={len(issues)}",
    )

    # 2) 正常加药
    a = chat("帮我加阿司匹林100mg每天一次")
    check("aspirin_needs_confirm", a.get("status") == "needs_confirmation")
    a2 = chat("确认", a["session_id"])
    collect_reminders(a2)
    check(
        "aspirin_reminder_created",
        any(x.get("type") == "reminder_created" for x in (a2.get("actions") or [])),
    )

    # 3) 相互作用：华法林 + 已有阿司匹林
    w = chat("帮我加华法林2.5mg每天一次")
    check("interaction_warned", "相互作用" in w.get("reply", ""), w.get("reply", "")[:60])
    w2 = chat("确认", w["session_id"])
    collect_reminders(w2)
    issues = safety()
    check(
        "safety_endpoint_interaction",
        any(
            "华法林" in (i.get("title", "") + i.get("why", ""))
            and "阿司匹林" in (i.get("title", "") + i.get("why", ""))
            and i.get("level") == "red"
            for i in issues
        ),
        f"issues={len(issues)}",
    )

    # 4) /agents/extract 用药抽取（只抽取不写库）
    e = client.post(
        f"{BASE}/agents/extract",
        json={"text": "帮我加阿司匹林100mg每天一次"},
        headers=H,
    ).json()
    med = e.get("medication") or {}
    check(
        "extract_medication",
        e.get("kind") == "medication"
        and ("阿司匹林" in (med.get("name") or "") or "阿司匹林" in (med.get("medication_name") or "")),
        f"kind={e.get('kind')} med={med}",
    )

    # 5) Safety-first：长病历也必须先经过 Safety（是否拦截取决于 LLM 复核）
    record = (
        "主诉：胸痛3小时。现病史：患者3小时前突发胸痛，伴呼吸困难。"
        "既往史：高血压10年。家族史：父亲冠心病。"
        "体格检查：血压160/95mmHg，心率98次/分。"
        "辅助检查：心电图示ST段抬高。诊断依据：急性冠脉综合征。"
        "治疗方案：立即转诊。出院医嘱：规律服药。入院日期：2026-11-01。出院日期：2026-11-05。"
    )
    r = chat(record)
    traces = client.get(f"{BASE}/agents/traces/{r['session_id']}", headers=H).json()
    agents = [t.get("agent_name") for t in traces]
    check(
        "safety_first_on_record",
        bool(agents) and agents[0] == "safety",
        f"agents={agents} status={r.get('status')}",
    )
    if r.get("status") == "blocked":
        chat("不用", r["session_id"])  # 清理 pending
finally:
    for reminder_id in created_reminders:
        try:
            client.delete(f"{BASE}/reminders/{reminder_id}", headers=H)
        except Exception:
            pass

print("cleanup reminders:", created_reminders)
print("OVERALL", "PASS" if ok else "FAIL")
