# 贴心小护士 · 后端 Agent 实施规格书

> 读者：编码模型 / 后端工程师。
> 配套文档（开工前必须读）：
> - [`docs/AGENT_DESIGN.md`](AGENT_DESIGN.md)：Agent 设计与架构（本文的上游）
> - [`docs/IMPLEMENTATION_SPEC.md`](IMPLEMENTATION_SPEC.md)：前端实施规格（契约必须对齐）
> - [`docs/IO_SPEC.md`](IO_SPEC.md)：输入输出契约（输出骨架 / 语音版 / 病历 8 模块）
>
> 本文只描述「做什么、接口长什么样、怎么验收、禁止什么」，不提供完整实现代码。
> 阶段范围：阶段 1（Safety / Router / Consult / Monitor / Planner / Document + 动作层 + 记忆/状态 + 评估），阶段 2（Medication），阶段 3（Diagnosis）只给接口占位。

---

## 0. 给编码模型的启动提示词

把下面这段连同本文件一起交给编码模型：

```text
你是资深 Python 后端工程师。请严格按 docs/AGENT_IMPLEMENTATION_SPEC.md 实现「贴心小护士」后端 Agent 层重构。

开工前必须先读：
- 本文件全部
- docs/AGENT_DESIGN.md
- docs/IMPLEMENTATION_SPEC.md（尤其 §1.3 后端缺口、附录 A）
- backend/app/graph/orchestrator.py、langgraph_app.py、streaming.py
- backend/app/api/agents.py、reminders.py
- backend/app/services/llm_service.py、rag_service.py、alert_service.py、document_parser.py
- backend/app/models/__init__.py、schemas.py、config.py、tasks/scheduler.py

实施顺序（每完成一步跑一次后端导入自检 / 单元测试，通过后再进入下一步）：
1) 骨架：AgentResult、pending store（state.py）、协调器 handle_message/handle_stream
2) Safety（规则召回 + LLM 复核 + 暂停询问 120）
3) Router 与 Consult（迁移现有逻辑，补 evidence）
4) Monitor（分析 + 指标抽取入库 + 二次确认）
5) Document（复用现有 OCR/抽取，接动作层）
6) API：/agents/chat、/agents/chat/stream、/agents/extract 响应扩展；SSE 增加 action/evidence
7) Medication：Drug/DrugInteraction/MedicationLog 模型 + seed + 安全审核 + 确认建提醒
8) 记忆/上下文：memory_service、context_builder（GSSC 轻量版）
9) 评估脚本 backend/tests/eval/run_eval.py
10) 全局自检：逐条过第 14 节验收清单、第 15 节反模式清单

硬性约束：
1. 不新增前端可见的接口破坏性变更；如需改响应结构，只增不改。
2. 所有 agent 输出必须走统一 AgentResult，禁止各写各的 dict。
3. 确定性判断（红旗词、用药过敏/相互作用/剂量）不得交给 LLM。
4. 无 LLM Key 时必须 Mock 兜底可跑通（沿用 llm_service 现有逻辑）。
5. 规格未覆盖的细节，选最小实现，并在代码注释标 SPEC-GAP。
6. 交付时给出：改动文件清单 + 每个文件做了什么 + 自检结果（逐条打勾）。
```

---

## 1. 范围与总原则

### 1.1 交付范围

| 层 | 内容 |
|---|---|
| 编排 | 统一协调器（意图分流、Safety 前置、pending 状态、流式/非流式） |
| Agent | Safety / Router / Consult / Monitor / Planner / Document / Medication（Diagnosis 仅占位） |
| 契约 | AgentResult（含 actions/evidence）、SSE 事件、ChatResponse 扩展 |
| 状态 | 外置 pending（confirm_write / safety_120 / diagnosis_session） |
| 记忆 | 工作 / 情景 / 语义 / 知识 四层 + 巩固/遗忘 |
| 上下文 | GSSC 轻量版（token 预算 + 分区 + 新近性） |
| 数据 | Drug / DrugInteraction / MedicationLog + 种子数据 |
| 评估 | 红旗测试集 + RAG Hit@3 跑分脚本 |

### 1.2 明确不做

- 不引入 Qdrant / Neo4j / MCP / LangGraph checkpointer。
- 不做真实外部医学 API（OrphaNet/OMIM/基因），诊断只用内置知识库。
- 不做医生端 / 管理员端。
- 不删除已有数据表（FollowUp 保留但停用，见 1.3）。
- 不做多 agent 自由协商（禁止 agent 之间传自然语言）。

### 1.3 三处冲突裁决（强制）

| # | 冲突 | 裁决 |
|---|---|---|
| 1 | 用药安全：前端规则 vs 后端 Drug 库 | **后端为权威**。新增 `DrugSafetyService` 与 `GET /api/medication/safety`；前端 `medicationSafety.ts` 降级为「后端不可用时的兜底」，正常情况只渲染后端返回的 `issues` |
| 2 | 语音/文本抽取：前端规则 vs 后端 LLM | **后端为权威**。新增 `POST /api/agents/extract`；前端 `parseHealthParams.ts` 降级为「接口失败时的兜底」 |
| 3 | 随访：保留 vs 删除 | **删除**。停用 `create_followup_tasks` 调度与 `followup_agent`；FollowUp 表保留（不删表），前端去掉待办随访/问卷子页 |

> 前端 spec 中与本裁决冲突的段落（§1.3 用药安全/语音抽取、§6.2 待办随访与问卷子页）以后端为准，前端实施时同步调整。

### 1.4 现状基线与收敛目标

现状存在**三份并行编排**：

- `app/graph/orchestrator.py::run_agent_graph`（旧手写版，**无任何引用，死代码**）；
- `app/graph/langgraph_app.py::run_langgraph`（StateGraph 版，被 `/api/agents/chat` 使用）；
- `app/graph/streaming.py::stream_agent_graph`（手写流式版，被 `/api/agents/chat/stream` 使用）。

**收敛目标**：

- **唯一运行时入口**：`orchestrator.py` 的 `handle_message()` / `handle_stream()`；
- **Agent 函数**：全部保留/新增在 `orchestrator.py`（共享同一套 `AgentContext`、`log_trace`）；
- `langgraph_app.py`：降级为「图定义与可视化」，可保留供答辩，**不得再被 API 调用**，只 import 共享 agent 函数、不重复实现；
- `streaming.py`：**删除**，逻辑并入 `handle_stream()`；
- 旧 `run_agent_graph`：**删除**。

---

## 2. 运行基线与目录结构

```
backend/app/
├── graph/
│   ├── orchestrator.py      # 协调器 + 全部 agent 函数（唯一运行时入口）
│   ├── state.py             # PendingStore（Redis 外置状态）
│   ├── context_builder.py   # GSSC 轻量版
│   ├── langgraph_app.py     # 图定义（保留，仅演示/可视化，不被 API 调用）
│   └── streaming.py         # 删除
├── services/
│   ├── drug_service.py      # 新增：药品库 + 安全审核
│   ├── memory_service.py    # 新增：四层记忆 + 巩固/遗忘
│   ├── alert_service.py     # 已有
│   ├── document_parser.py   # 已有：抽取 prompt 复用
│   └── ...
├── api/
│   ├── agents.py            # 改为调用 handle_message/handle_stream
│   ├── reminders.py         # 增加 checkin
│   └── medication.py        # 新增：/medication/safety
└── tests/eval/              # 新增：评估脚本与数据
```

---

## 3. 非功能要求

| 项 | 要求 |
|---|---|
| 超时 | LLM 调用 60s（沿用 `llm_service`）；RAG 检索 10s；外部语音 10s |
| 降级 | LLM 不可用 → Mock；RAG 失败 → 关键词；Redis 不可用 → pending 失效但主流程不阻塞 |
| 日志 | 每个 agent 必须写 `AgentTrace`；异常必须记录到 trace 的 `output_data.error` |
| 幂等 | `MedicationLog` 唯一键 `(reminder_id, log_date, slot)`；服药提醒去重沿用 Redis `SET NX` |
| 隐私 | 日志与 trace 不落完整病历原文，只落摘要（前 200 字） |
| 合规 | 所有面向用户的 AI 输出必须包含 `DISCLAIMER`；诊断类输出强制 |

---

## 4. AgentResult 契约

```python
from typing import Literal, TypedDict

class Action(TypedDict, total=False):
    type: str            # record_created | reminder_created | navigate | toast | safety_alert
    record_id: int
    reminder_id: int
    target: str          # navigate 用，如 "/medication"
    level: str           # toast 用：success | warning | error
    message: str
    summary: str

class Evidence(TypedDict, total=False):
    source: str          # 指南名 / "知识图谱"
    title: str
    snippet: str
    relation: str
    score: float

class Presentation(TypedDict, total=False):
    summary: str             # 结论，≤20 字
    key_points: list[str]    # 关键信息，≤3 条
    action_items: list[str]  # 用户该做的事，1~2 件
    boundary: str            # 就医边界 + 免责
    tts_text: str            # 语音版（去符号、数字口语化）

class AgentResult(TypedDict, total=False):
    agent: str
    status: Literal["ok", "needs_confirmation", "blocked", "error"]
    reply: str                    # 全文兜底（无障碍 / 前端回退）
    payload: dict
    actions: list[Action]         # 系统动作：写库 / 导航 / 提示
    evidence: list[Evidence]
    presentation: Presentation    # 结构化呈现，见 docs/IO_SPEC.md §3.1
    trace: dict                   # {duration_ms, model, fallback, error}
```

**规则**：

- `status="needs_confirmation"` 时，**必须**同时把 pending 写入 `state.py`（见 §7）；
- `status="blocked"` 仅用于 Safety 暂停问 120；
- `actions` 只描述「发生了什么 / 前端该做什么」，**不允许**包含 agent 之间的控制指令；
- `evidence` 供前端展示「依据」，同时写入 `AgentTrace.output_data.evidence`；
- `presentation` 按 `docs/IO_SPEC.md` §3.1 生成；问答类必须含 `summary` 与 `tts_text`；`reply` 保留全文兜底。

---

## 5. 各 Agent 规格

### 5.1 Safety（安全分诊）

**输入**：`message`（已转文本）、可选 `history`。

**三层漏斗**：

1. **L1 规则召回**（`safety_rules.py` 或 orchestrator 内常量）：
   - 红旗词表（可扩展）：胸痛 / 心口疼 / 胸口压榨 / 胸闷 / 呼吸困难 / 喘不上气 / 憋气 / 晕厥 / 昏倒 / 意识不清 / 口角歪斜 / 说话不清 / 大舌头 / 半边无力 / 单侧麻 / 剧烈头痛 / 抽搐 / 呕血 / 黑便 / 喉头水肿；
   - 否定窗口：命中词前 6 字内出现 `没有/不/没/无` → 标记 `negated`，降低置信；
   - 输出候选：`[{term, negated}]`。
2. **L2 LLM 复核**（仅当有候选时调用；无 Key 跳过）：
   - 输入：原话 + 候选词 + 最近 2 轮；
   - 输出 JSON：`{"is_emergency": bool, "severity": "red|orange|none", "belongs_to": "self|other|past|hypothetical", "reason": "..."}`；
   - 复用 `llm_service.extract_json`。
3. **L3 决策**：
   - 有候选且（LLM 确认 或 LLM 不可用）→ `blocked`，暂停问 120；
   - 有候选且 LLM 判否（否定/历史/他人）→ 正常继续，trace 记录；
   - 无候选 → 正常继续。

**暂停输出**：

```python
{
  "agent": "safety", "status": "blocked",
  "reply": "您描述的情况可能有危险，需要我帮您拨打 120 吗？",
  "payload": {"kind": "safety_120", "red_flags": ["胸痛"]},
}
```

同时 `PendingStore.set(kind="safety_120", original_message=..., original_intent=None, ttl=600)`。

**拒绝后继续**：记录 trace；用 `original_message` 重放路由（**跳过 Safety**，否则无限循环）；回复保留一句「如症状加重请立即就医」。

**验收**：

- 「我胸口疼得厉害」→ blocked；
- 「我没有胸痛，就是想问饮食」→ 不 blocked（LLM 可用时；无 Key 时允许误报，但必须可解释）；
- 用户回「不用」→ 继续原链路；回「要」→ 返回 `safety_alert` action。

### 5.2 Router

- 规则优先（沿用现有关键词）；
- 低置信度 / 无命中时可选 LLM 分类（无 Key 走规则默认 `consult`）；
- 输出 `intent ∈ {consult, monitor, planner, document, medication, diagnosis}`；
- 写 `AgentTrace`（action=`intent_classification`）。

### 5.3 Consult

- 输入：`message`、`history`、患者画像、近期记录、RAG 片段、可选 `alert_context`；
- 复用 `document_parser` 的免责声明与 `llm_service.chat`；
- **evidence**：RAG 命中片段 → `[{source, title, snippet, score}]`；
- 无 Key → Mock（沿用现有）。
- 「讲讲这条预警」：入参带 `alert_context`，输出口语化解释 + 建议。

### 5.4 Monitor（分析 + 抽取入库）

两种模式，由 Router 或 pending 决定。

**分析模式**：读最近记录/趋势 → 生成概览 + 异常 + 建议（沿用现有 `monitor_agent`，补 evidence=近期记录摘要）。

**抽取模式（新增）**：

1. 抽取：优先 LLM（复用 `document_parser.EXTRACT_LAB_SYSTEM`），失败回退正则（复用 `_LAB_PATTERNS`）；
2. 得到 `metrics: [{record_type, value, unit, context, systolic, diastolic}]`；
3. 若为空 → 回「没太听清，能再说一次吗」，不写 pending；
4. 否则 → `status="needs_confirmation"`，pending `kind="confirm_write", agent="monitor", payload={"metrics": [...]}`；
5. 回复："我听到您说，空腹血糖 6.8，对吗？"（含语音播报由前端处理）。

**确认执行**：

```python
for m in metrics:
    extra = {}
    if m["record_type"] == "blood_pressure":
        extra["systolic"] = m.get("systolic")
        extra["diastolic"] = m.get("diastolic")
    elif m.get("context"):
        extra["type"] = m["context"]           # 血糖/血脂场景

    record = await HealthService(db).create_record(
        patient,
        HealthRecordCreate(
            record_type=RecordType(m["record_type"]),
            value=float(m["value"]),
            unit=m.get("unit", ""),
            extra_data=extra,
        ),
    )
    await AlertService(db).evaluate_record(patient, record)
    actions.append({
        "type": "record_created",
        "record_id": record.id,
        "summary": f"已记录 {m.get('name', m['record_type'])}",
    })
```

### 5.5 Planner

- 复用现有提示词，但**必须解析 LLM 返回的 JSON**（diet/exercise/monitoring），失败时回退默认项并标记 `fallback=true`；
- 写 `CarePlan`（现有 `create_care_plan` 的硬编码必须移除）；
- 输出 `care_plan` + action `{"type": "navigate", "target": "/me/plans"}`。

### 5.6 Document

- 复用现有 `DocumentService.process/dispatch`（OCR → 分类 → 抽取 → 确认 →归档）；
- 化验单 → `record_created` actions；处方 → `reminder_created` actions；
- 门诊病历/出院小结：当前 `dispatch` 返回 `no_action`，**阶段 1 保持**（不强行归档），在 trace 标注 `not_supported`；
- 病历/出院小结的解释输出按 `docs/IO_SPEC.md` §4 的 8 模块渲染，抽取 schema 需补 `status_text` 与 `questions_to_ask`。

### 5.7 Medication（阶段 2）

**三种能力**：

1. **抽取**：复用 `document_parser.EXTRACT_PRESCRIPTION_SYSTEM`；得到 `medications[]` → 安全审核 → `needs_confirmation` → 确认后 `ReminderService.create`；
2. **安全审核**（`DrugSafetyService.check(patient, meds) -> list[SafetyIssue]`）：
   - 过敏交叉：`Patient.allergies` 拆分 vs `Drug.allergy_terms` → `red`；
   - 相互作用：两两查 `DrugInteraction` → `major=red / moderate=orange / minor=yellow`；
   - 剂量：`dose` vs `Drug.dose_min/max` → `orange`；
   - 重复：同 `generic_name` ≥2 条 → `orange`；
   - 输出 `SafetyIssue{level, title, why, advice, drug_names}`。
3. **咨询**：RAG 检索药品知识，回答「饭前还是饭后」「漏服怎么办」。

**确认执行**：建 `MedicationReminder`，返回 `reminder_created` + `navigate /medication`。

**安全提示接口**：`GET /api/medication/safety` → `{"issues": [SafetyIssue]}`（前端渲染；后端不可用才用前端本地规则）。

### 5.8 Diagnosis（阶段 3 占位）

- 阶段 1/2 只建空函数 `diagnosis_agent`，返回 `{"status":"error","reply":"诊断功能建设中"}`，Router 不路由到它；
- 阶段 3 实现：表型抽取 → RAG + 知识图谱匹配 → 证据融合排序 → 输出「可能方向 + 依据 + 危险信号 + 就医建议」；
- **必须**在 Safety 之后（Safety 已是全局前置）。

---

## 6. 协调器流程

```python
async def handle_message(db, patient, message, session_id=None) -> dict:
    session_id = session_id or str(uuid4())
    history = await load_history(db, patient.id, session_id)
    ctx = AgentContext(db, patient, session_id, history)

    await save_message(db, patient.id, session_id, "user", message)
    if is_new_session:
        await enforce_session_limit(db, patient.id)

    # 1) 先查 pending
    pending = await PendingStore.get(patient.id, session_id)
    if pending:
        resumed = await resume_pending(db, patient, message, pending)
        if resumed is not None:
            await save_message(..., "assistant", resumed["reply"])
            return finalize(resumed, session_id)

    # 2) Safety
    safety = await safety_agent(ctx, message)
    if safety["status"] == "blocked":
        await PendingStore.set(... kind="safety_120", original_message=message)
        return finalize(safety, session_id)

    # 3) 路由 + 执行
    intent = await router_agent(ctx, message)
    result = await dispatch_intent(ctx, intent, message)

    # 4) 落库 / 记忆 / 上下文
    await save_message(..., "assistant", result["reply"])
    await save_context(patient, session_id, intent)
    return finalize(result, session_id)
```

`handle_stream()` 结构相同，只是把 `reply` 逐 token 产出，并额外产出 `action` / `evidence` 事件。

**finalize 返回**（供 API 组装）：

```python
{
  "reply": ..., "session_id": ..., "intent": ...,
  "status": ..., "actions": [...], "evidence": [...],
  "agent_traces": ctx.traces, "care_plan": ..., "followup": None,
}
```

---

## 7. 状态与中断

**存储**：Redis，Key = `pending:{patient_id}:{session_id}`，TTL = 600s。

```python
class PendingStore:
    @staticmethod
    async def get(patient_id, session_id) -> dict | None
    @staticmethod
    async def set(patient_id, session_id, data: dict, ttl: int = 600)
    @staticmethod
    async def clear(patient_id, session_id)
```

**data 结构**：

```json
{
  "kind": "confirm_write | safety_120 | diagnosis_session",
  "agent": "monitor",
  "original_message": "我早上空腹血糖6.8",
  "original_intent": "monitor",
  "payload": {"metrics": [...]},
  "created_at": "2026-11-05T..."
}
```

**恢复逻辑**：

```python
async def resume_pending(db, patient, message, pending):
    if pending["kind"] == "confirm_write":
        if is_confirm(message):
            result = await execute_pending(db, patient, pending)   # 写库
            await PendingStore.clear(...)
            return result
        if is_cancel(message):
            await PendingStore.clear(...)
            return {"status": "ok", "reply": "好的，已取消。", "agent": pending["agent"]}
        await PendingStore.clear(...)
        return None            # 当新消息处理
    if pending["kind"] == "safety_120":
        if is_yes(message):
            await PendingStore.clear(...)
            return {"status": "ok", "reply": "请立即拨打 120，或点右侧紧急呼叫。",
                    "actions": [{"type": "safety_alert", "summary": "已提示拨打120"}]}
        await PendingStore.clear(...)
        if is_no(message):
            log_declined_120(...)
            return await replay_skip_safety(db, patient, pending["original_message"], ...)
        return await replay_skip_safety(...)
    if pending["kind"] == "diagnosis_session":
        return await diagnosis_agent(...)   # 阶段 3
    return None
```

**规则词表**（可扩展）：

```python
CONFIRM_WORDS = ("确认", "对", "好", "是", "可以", "行", "没错", "嗯", "记下来", "保存")
CANCEL_WORDS  = ("不", "不用", "取消", "算了", "不对", "重来", "别")
```

**约束**：

- 只保留一个 pending，新覆盖旧；
- Redis 异常 → 视为无 pending，主流程继续；
- pending 过期 → 视为无 pending。

---

## 8. 记忆分层

| 层 | 存储 | 写入时机 | 读取时机 |
|---|---|---|---|
| 工作 | Redis `patient_context:{id}` + `pending` | 每轮结束 / 待确认 | 每轮开始 |
| 情景 | `AgentTrace` + `ChatMessage` | 每轮 | 分析/复盘 |
| 语义 | `Patient`（疾病/过敏/用药/偏好） | 巩固任务 | 所有 agent |
| 知识 | `KnowledgeChunk`（pgvector） | seed | RAG |

**巩固（Consolidate）**：

- 触发：会话结束（前端切会话 / 30 分钟无活动，可由后台任务定时扫描）；
- 逻辑：从最近会话抽取「患者新事实」（新症状/新用药/过敏/习惯），写回 `Patient.health_profile` 或 `medications` 字段；
- 只写「新且确定」的事实，不确定的不写；
- 记录 `AgentTrace(action="memory_consolidate")`。

**遗忘（Forget）**：

- 会话上限沿用 20（现有 `enforce_session_limit`）；
- 可选：按 `AgentTrace.created_at` 清理超过 N 天的低重要性记录（默认关闭，演示环境不启用）。

---

## 9. 上下文工程（GSSC 轻量版）

改造 `build_consult_messages` / `build_planner_messages`：

1. **Token 预算**：`max_tokens≈3000`，中文按 1 字≈1 token 估算；系统指令预留 20%；
2. **分区结构**：

```text
[Role]
你是「贴心小护士」…

[Patient Context]
慢病：…；过敏：…；近期指标：…

[Evidence]
[1] 《中国高血压防治指南》…

[History]
user: …
assistant: …

[Task]
用户：…

[Output]
…（免责声明 / JSON 格式要求）
```

3. **选择**：综合分 = 相关性×0.7 + 新近性×0.3；超预算时先丢最老历史，再截断 Evidence；
4. **压缩**：超限时按分区截断并标注 `[... 内容已压缩 ...]`。

> 不要求精确 tokenizer，估算即可；不引入 tiktoken 等新依赖。

---

## 10. API 与 SSE 契约

### 10.1 `POST /api/agents/chat`（非流式）

**响应扩展**（只增不改）：

```json
{
  "reply": "...",
  "session_id": "...",
  "agent_traces": [{"agent": "router", "action": "...", "duration_ms": 12}],
  "care_plan": null,
  "intent": "monitor",
  "status": "ok",
  "actions": [{"type": "record_created", "record_id": 123, "summary": "已记录空腹血糖 6.8"}],
  "evidence": [{"source": "中国2型糖尿病防治指南", "title": "血糖控制目标", "score": 0.82}]
}
```

`schemas.ChatResponse` 增加 `intent/status/actions/evidence`（默认空）。

### 10.2 `POST /api/agents/chat/stream`（SSE）

事件类型统一为 `data: {"type": ..., ...}`：

| type | 载荷 | 说明 |
|---|---|---|
| `trace` | `{"data": {...}}` | 每次 agent 执行后 |
| `token` | `{"data": "文本片段"}` | LLM 流式 |
| `action` | `{"data": {...}}` | 写库/导航/提示 |
| `evidence` | `{"data": {...}}` | 证据来源 |
| `done` | `{"session_id","intent","status","actions","evidence"}` | 结束 |
| `error` | `{"message"}` | 异常 |

前端 `client.ts` 的 `chatStream` 需要透传 `action`/`evidence`（前端 spec 已预留扩展点）。

### 10.3 `POST /api/agents/extract`（新增，冲突 2 的落地）

```json
// 请求
{"text": "空腹血糖6.8"}
// 响应
{"kind": "metric",
 "metric": {"record_type": "blood_glucose", "value": 6.8, "unit": "mmol/L", "extra_data": {"type": "fasting"}}}
```

- `kind ∈ {metric, medication, none}`；
- **只抽取，不写库**；写库仍走 `POST /health/records` / `POST /reminders`；
- 前端在 `parseHealthParams` 失败时调用。

### 10.4 `GET /api/medication/safety`（新增，冲突 1 的落地）

```json
{"issues": [
  {"level": "red", "title": "青霉素过敏与阿莫西林冲突",
   "why": "您对青霉素过敏", "advice": "请联系医生更换药物", "drug_names": ["阿莫西林"]}
]}
```

### 10.5 `POST /api/reminders/{id}/checkin`（新增，对齐前端附录 A.1）

```json
{"date": "2026-11-05", "slot": "08:00", "status": "taken"}
// 响应
{"ok": true}
```

- 幂等：`UNIQUE(reminder_id, log_date, slot)`，重复提交覆盖状态；
- `status ∈ {taken, skipped}`。

### 10.6 停用接口

- `GET /api/follow-ups`、`POST /api/follow-ups/{id}/submit`：**保留代码但不再被调度/前端使用**（标记 `deprecated`）；
- `tasks/scheduler.py` 的 `create_followup_tasks`：从 lifespan 移除调度注册。

---

## 11. 数据模型与种子

### 11.1 新增模型（`app/models/__init__.py`）

```python
class Drug(Base):
    __tablename__ = "drugs"
    id: int
    generic_name: str          # 通用名，唯一
    brand_names: list          # JSONB
    category: str              # 分类
    route: str | None
    dosage_forms: list         # JSONB
    dose_min: float | None
    dose_max: float | None
    dose_unit: str | None
    allergy_terms: list        # JSONB：用于过敏交叉匹配的词
    contraindications: str | None
    notes: str | None

class DrugInteraction(Base):
    __tablename__ = "drug_interactions"
    id: int
    drug_a: str                # 通用名
    drug_b: str
    severity: str              # minor | moderate | major
    advice: str

class MedicationLog(Base):
    __tablename__ = "medication_logs"
    id: int
    patient_id: int
    reminder_id: int
    log_date: date
    slot: str                  # "08:00"
    status: str                # taken | skipped
    recorded_at: datetime
    __table_args__ = (UniqueConstraint("reminder_id", "log_date", "slot"),)
```

> 迁移说明：项目用 `Base.metadata.create_all`（lifespan），**新表会自动创建**；已有表不加列（可观测字段统一塞 `AgentTrace.output_data` JSONB，见 §13）。

### 11.2 种子（`scripts/seed.py`）

- 内置 15~30 种常用慢病药：二甲双胍、格列美脲、阿司匹林、氯吡格雷、华法林、硝苯地平、氨氯地平、缬沙坦、美托洛尔、阿托伐他汀、瑞舒伐他汀、辛伐他汀、克拉霉素、红霉素、西柚（作为食物相互作用提示）……；
- 10~20 条常见相互作用：阿司匹林/氯吡格雷 + 华法林、二甲双胍 + 含碘造影剂、硝苯地平 + 西柚、他汀 + 大环内酯类等；
- 幂等：按 `generic_name` 判重。

---

## 12. 错误处理与降级

| 场景 | 处理 |
|---|---|
| LLM 超时/不可用 | 走 `llm_service` Mock；trace 标 `fallback=true` |
| RAG 检索失败 | 降级关键词（现有逻辑）；evidence 标注 `degraded` |
| Redis 不可用 | pending 读写 try/except，视为无 pending，不阻塞 |
| 数据库写失败 | 回滚当前事务，返回 `status="error"` + 友好文案 |
| Safety LLM 复核失败 | 按规则命中处理（保守） |
| 抽取结果为空 | 不写 pending，回「没太听清」 |
| 用户发无关消息且有待确认 | 清 pending，走正常路由 |

---

## 13. AgentTrace 可观测字段

**不新增数据库列**，全部写入现有 `output_data`（JSONB）：

```json
{
  "status": "ok",
  "model": "deepseek-chat",
  "tokens_in": 812,
  "tokens_out": 96,
  "fallback": false,
  "evidence": [{"source": "...", "title": "..."}],
  "error": null
}
```

前端 `AgentTrace` 组件可选展示（当前前端 spec 说不渲染，保持不变；数据供后端排查与答辩）。

---

## 14. 验收清单

### 14.1 Safety

- [ ] 「我胸口疼得厉害」→ `status=blocked`，pending 写入；
- [ ] 用户回「不用」→ 继续原链路，且 trace 记录「拒绝120」；
- [ ] 用户回「要」→ 返回 `safety_alert` action；
- [ ] 「我没有胸痛」在 LLM 可用时不 blocked（无 Key 允许误报但需 trace 可解释）。

### 14.2 Monitor 抽取

- [ ] 「我早上空腹血糖6.8」→ `needs_confirmation`；
- [ ] 回「确认」→ `HealthRecord` 落库 + `record_created` action；
- [ ] 回「取消」→ 不落库；
- [ ] 回无关消息 → pending 清除，正常路由；
- [ ] 超时 10 分钟后 pending 失效。

### 14.3 Medication

- [ ] 「帮我加阿司匹林100mg每天一次」→ 安全审核 → `needs_confirmation`；
- [ ] 确认 → `MedicationReminder` 落库 + `GET /api/medication/safety` 能返回过敏/相互作用/剂量问题；
- [ ] 打卡接口幂等（重复提交不重复计数）。

### 14.4 API / SSE

- [ ] `/agents/chat` 响应含 `intent/status/actions/evidence`；
- [ ] `/agents/chat/stream` 能产出 `action` / `evidence` 事件；
- [ ] `/agents/extract` 只抽取不写库；
- [ ] 前端旧字段（reply/session_id/agent_traces/care_plan）不破坏。

### 14.5 记忆 / 上下文

- [ ] 巩固任务能把「新过敏」写回 Patient；
- [ ] `build_consult_messages` 超预算时按分区截断，不报错；
- [ ] 无 Key 全链路可跑通。

### 14.6 评估

- [ ] `backend/tests/eval/run_eval.py` 能输出红旗召回/精确；
- [ ] RAG Hit@3 可复现。

### 14.7 工程

- [ ] `python -c "from app.main import app"` 通过；
- [ ] 无新增前端依赖、无破坏性响应变更；
- [ ] 所有 agent 输出统一 AgentResult，无裸 dict。

### 14.8 输出规格（对齐 IO_SPEC）

- [ ] 问答类回复带 `presentation.summary`（≤20 字）与 `tts_text`；
- [ ] 危险信号回复把「立即就医」放第一句；
- [ ] 报指标/报用药走二次确认，仅询问数字不弹确认；
- [ ] 病历解释覆盖 8 模块，缺失字段有降级文案。

---

## 15. 反模式清单（禁止项）

| 禁止 | 为什么 | 正确做法 |
|---|---|---|
| 用 LLM 做「是否打120」/过敏/剂量判断 | 不可复现、会漏判 | 规则 + 服务 |
| agent 之间传自然语言 | 不可控、难追踪 | 统一 AgentResult + 协调器 |
| 三份编排并存 | 改一处漏两处 | 收敛到 orchestrator |
| 把 db/patient 塞进 LangGraph state | 无法序列化、阻碍后续 | 传 id / 闭包注入 |
| 抽取后直接写库 | 语音识别易错 | 先 needs_confirmation |
| 用药安全只在前端 | 可绕过、拿不到药品库 | 后端 DrugSafetyService |
| 给已有表强加列靠 create_all | 不会生效 | 新表用 create_all，旧字段进 JSONB |
| 诊断输出不带免责声明 | 合规风险 | 强制 DISCLAIMER |
| 评估只做单元测试不做数据集 | 无法证明效果 | 红旗集 + Hit@3 |

---

## 附录 A：prompt 复用与模板

| 用途 | 复用/新增 |
|---|---|
| 指标抽取 | 复用 `document_parser.EXTRACT_LAB_SYSTEM` + `_LAB_PATTERNS` 回退 |
| 处方抽取 | 复用 `document_parser.EXTRACT_PRESCRIPTION_SYSTEM` |
| 病历抽取 | 复用 `document_parser.EXTRACT_MEDICAL_RECORD_SYSTEM` |
| Planner | 复用现有，改为解析 JSON |
| Safety 复核 | 新增（见下） |

**Safety 复核 prompt 骨架**：

```text
你是医疗安全分诊助手。判断用户这句话是否描述「当前、本人、真实、急性」的危险信号。
用户原话：{message}
命中词：{terms}
要求：只输出 JSON：
{"is_emergency": true/false, "severity": "red|orange|none",
 "belongs_to": "self|other|past|hypothetical", "reason": "一句话"}
```

---

## 附录 B：实施顺序与验收节奏

| 步骤 | 交付 | 通过标准 |
|---|---|---|
| 1 | AgentResult + PendingStore + 协调器骨架 | 单测：pending 读写/过期；导入通过 |
| 2 | Safety | 14.1 全过 |
| 3 | Router + Consult | 意图/问答正常，evidence 产出 |
| 4 | Monitor 抽取 | 14.2 全过 |
| 5 | Document 接线 | 化验单/处方 dispatch 正常 |
| 6 | API/SSE 扩展 | 14.4 全过 |
| 7 | Medication | 14.3 全过 |
| 8 | 记忆 + 上下文 | 14.5 全过 |
| 9 | 评估脚本 | 14.6 全过 |
| 10 | 全局自检 | 14 全勾选、15 零违反 |

每步结束后：导入自检通过 + 对应验收小节自检 + 报告改动文件。
