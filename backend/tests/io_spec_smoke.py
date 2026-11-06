"""IO_SPEC 增量验收冒烟测试（presentation / 确认收窄 / 服药分流 / 8 模块）。

运行：在 backend 目录执行 `python tests/io_spec_smoke.py`
测试后会由外层 SQL 清理 chat/traces/plans/alerts/reminders/logs。
"""

import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

from app.graph.presentation import to_tts_text  # noqa: E402

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8080/api")
client = httpx.Client(timeout=180)

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


def check_presentation(name: str, payload: dict) -> None:
    presentation = payload.get("presentation") or {}
    check(f"{name}_presentation", bool(presentation.get("summary")), f"summary={presentation.get('summary')}")
    check(f"{name}_tts", bool(presentation.get("tts_text")), "")
    check(f"{name}_actions", 1 <= len(presentation.get("action_items") or []) <= 2, "")
    check(f"{name}_summary_len", len(str(presentation.get("summary") or "")) <= 20, "")
    check(f"{name}_points_len", len(presentation.get("key_points") or []) <= 3, "")


# 0) TTS 数字口语化
tts = to_tts_text("血压140/90，血糖6.8，请拨打120")
check("tts_bp", "一百四十比九十" in tts, tts)
check("tts_decimal", "六点八" in tts, tts)
check("tts_120", "一百二十" in tts, tts)

# 1) 询问数字：不弹确认，走 monitor 分析
q = chat("血糖6.8算高吗")
check("metric_question_status", q.get("status") == "ok", f"status={q.get('status')}")
check("metric_question_intent", q.get("intent") == "monitor", f"intent={q.get('intent')}")
check_presentation("metric_question", q)

# 2) 报指标：二次确认
m = chat("我早上空腹血糖6.8")
check("metric_report_needs_confirm", m.get("status") == "needs_confirmation", f"status={m.get('status')}")
check_presentation("metric_report", m)
chat("取消", m["session_id"])

# 3) 已服药：写 MedicationLog，不建提醒
i = chat("吃了片阿司匹林")
check("intake_needs_confirm", i.get("status") == "needs_confirmation", f"status={i.get('status')}")
check("intake_intent", i.get("intent") == "medication", f"intent={i.get('intent')}")
check("intake_reply", "吃了" in i.get("reply", ""), i.get("reply", "")[:60])
check_presentation("intake", i)
ic = chat("确认", i["session_id"])
action_types = [a.get("type") for a in ic.get("actions", [])]
check("intake_confirm_log", "record_created" in action_types and "reminder_created" not in action_types, str(action_types))
check("intake_confirm_reply", "已记下" in ic.get("reply", ""), ic.get("reply", "")[:60])

# 4) 未来用药：建 MedicationReminder
r = chat("以后每天吃一片阿司匹林")
check("reminder_needs_confirm", r.get("status") == "needs_confirmation", f"status={r.get('status')}")
check_presentation("reminder", r)
rc = chat("确认", r["session_id"])
action_types = [a.get("type") for a in rc.get("actions", [])]
check("reminder_confirm_created", "reminder_created" in action_types, str(action_types))

# 5) 拍药盒：明确降级
p = chat("拍个药盒")
check("pillbox_degraded", "不支持" in p.get("reply", "") and "手动" in p.get("reply", ""), p.get("reply", "")[:80])
check_presentation("pillbox", p)

# 6) 情绪求助：Consult 安抚，无独立情绪模型
e = chat("我有点怕")
check("emotion_soothing", "先别着急" in e.get("reply", ""), e.get("reply", "")[:60])
check_presentation("emotion", e)

# 7) 危险信号：置顶就医 + presentation
s = chat("我胸口疼得厉害")
check("safety_blocked", s.get("status") == "blocked", f"status={s.get('status')}")
check("safety_first_sentence", "紧急" in s.get("reply", "") or "立即" in s.get("reply", ""), s.get("reply", "")[:60])
check_presentation("safety", s)
chat("不用", s["session_id"])

# 8) 病历 8 模块
record = (
    "出院小结：入院诊断：2型糖尿病。出院诊断：1、2型糖尿病 2、高脂血症。"
    "主诉：口干多饮多尿1个月。既往史：否认高血压。"
    "辅助检查：空腹血糖12.5mmol/L，糖化血红蛋白9.5%。"
    "出院医嘱：低盐低脂糖尿病饮食；出院1周后内分泌科门诊复诊；按时服用二甲双胍肠溶片0.5g每日2次；防跌倒。"
)
d = chat(record)
check("document_intent", d.get("intent") == "document", f"intent={d.get('intent')}")
check("document_needs_confirm", d.get("status") == "needs_confirmation", f"status={d.get('status')}")
reply = d.get("reply", "")
for mark in "①②③④⑤⑥⑦⑧":
    check(f"document_module_{mark}", mark in reply, "")
check("document_status_text", "现在情况" in reply, "")
check("document_questions", "建议问医生" in reply, "")
check_presentation("document", d)
chat("取消", d["session_id"])

# 9) 诊断红线
g = chat("我头晕头痛、乏力，可能是什么病")
check("diagnosis_intent", g.get("intent") == "diagnosis", f"intent={g.get('intent')}")
check("diagnosis_no_forbidden", not any(w in g.get("reply", "") for w in ("确诊", "就是", "诊断为")), g.get("reply", "")[:80])
check("diagnosis_possible", "可能方向" in g.get("reply", ""), "")
check_presentation("diagnosis", g)

# 10) 流式 done 事件带 presentation
done_event = None
with client.stream(
    "POST", f"{BASE}/agents/chat/stream", headers=H, json={"message": "你好"}
) as resp:
    resp.raise_for_status()
    for line in resp.iter_lines():
        if line.startswith("data: "):
            event = json.loads(line[6:])
            if event.get("type") == "done":
                done_event = event
check("stream_done_presentation", bool((done_event or {}).get("presentation")), "")

print("OVERALL", "PASS" if ok else "FAIL")
