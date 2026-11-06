# 贴心小护士 · Agent 设计说明

> 版本：v1.0（需求讨论稿）
> 范围：患者端（移动 H5，5 个 tab）；家人端、医生端不在本版范围。
> 配套：`docs/AGENT_IMPLEMENTATION_SPEC.md`（后端实施）、`docs/IMPLEMENTATION_SPEC.md`（前端）、`docs/IO_SPEC.md`（输入输出契约）。

## 1. 设计原则

1. **确定性优先**：红旗识别、用药过敏/相互作用/剂量、阈值预警 → 规则/服务；语义理解与生成 → LLM。
2. **星型编排**：agent 之间不直接互调，统一经协调器（Graph）+ 共享状态，保证可追踪、防死循环。
3. **结构化通信**：agent 输出 `AgentResult`，不传自然语言。
4. **谁写库谁负责**：写数据由后端 service 执行，前端只负责呈现结果与跳转，agent 不碰 UI。
5. **少而清晰**：agent 数量控制在 8 个以内，每个职责单一。

## 2. Agent 花名册

| # | Agent | 职责 | 类型 | 阶段 |
|---|---|---|---|---|
| 1 | Safety（安全分诊） | 红旗识别 → 暂停询问 120 → 用户拒绝则继续 | 规则 + LLM | 1 |
| 2 | Router | 意图分流（consult/monitor/planner/document/medication/diagnosis） | 规则 + LLM 兜底 | 1 |
| 3 | Consult | 通用问答、RAG、讲预警 | LLM | 1 |
| 4 | Monitor | ①指标分析 ②指标抽取入库 | LLM + 规则 | 1 |
| 5 | Planner | 生成饮食/运动/监测方案 | LLM | 1 |
| 6 | Document | 报告/病历 OCR → 分类 → 抽取 → 归档 | OCR + LLM | 1 |
| 7 | Medication | 用药抽取 + 安全审核 + 咨询 | LLM + 规则 | 2 |
| 8 | Diagnosis | 症状 → 初步方向 + 就医建议 | LLM + RAG | 3 |

- **已删除**：Followup（随访页已取消）。
- **已合并**：Warning（预警改为对话消息流，职能并入 Consult）。
- **非 agent**：全局语音球是入口/呈现层；SOS 是功能，由 Safety 流程处理。

## 3. 拓扑与典型链路

```
用户输入（文字/语音/拍照/SOS/预警触发）
        │
   ┌────▼─────┐
   │  Safety  │ ← 红旗命中则暂停询问 120
   └────┬─────┘
        │ 正常/拒绝120
   ┌────▼────┐
   │ Router  │
   └────┬────┘
   ┌────┼──────┬────────┬─────────┬──────────┐
   ▼    ▼      ▼        ▼         ▼          ▼
Consult Monitor Planner Document Medication Diagnosis(阶段3)
```

典型链路：

1. **报指标**：Safety → Router(monitor) → Monitor 抽取 → 工作记忆「待确认」 → 用户确认 → 写 HealthRecord + 触发预警。
2. **用药**：Safety → Router(medication) → Medication 抽取 → 药品库安全审核 → 确认 → 建 MedicationReminder。
3. **症状咨询**：Safety → Router(consult) → Consult 回答 →（症状明显时）Planner 出方案。
4. **传报告**：Document（OCR→抽取）→ 确认页 → dispatch（化验单写记录 / 处方建提醒）。
5. **预警讲解**：预警触发 → Consult（带 alert 上下文）→ 口语解释 + 建议。
6. **诊断**：Safety（放行）→ Router(diagnosis) → Diagnosis 查知识库 → 初步方向 + 就医建议。

## 4. Safety Agent（安全分诊）

不用纯规则（会漏报/误报），采用**三层漏斗**：

```
L1 规则召回（宁滥勿缺）    同义词库 + 否定词窗口
        │ 命中
L2 LLM 语义复核            判断是否「当前、本人、真实、急性」
        │ 输出 {is_emergency, severity, belongs_to, reason}
L3 决策 + 兜底
   ├─ 规则命中 + LLM 确认 → 暂停，问「需要帮您拨打120吗」
   ├─ 规则命中 + LLM 判否 → 正常继续（记 trace）
   ├─ 规则未命中 + 含症状词 → 可选 LLM 补扫
   └─ LLM 不可用/超时 → 按规则命中处理（保守）
```

**交互流程**：

```
命中 → 【暂停】记住 {原消息, 原意图, 红旗项}
     → 回复「您描述的情况可能有危险，需要帮您拨打120吗？」
        ├─ 用户「要」   → 走 SOS / 120
        ├─ 用户「不要」 → 记录 + 取回原链路继续
        └─ 用户说别的   → 视为「不要」，继续
```

**3 条安全护栏**：
1. 拒绝后不静默继续，保留一句「如症状加重请立即就医」；
2. 记录「用户拒绝拨打 120」到 `AgentTrace`（留痕 + 免责）；
3. 提供「联系紧急联系人」作为次选。

## 5. 通信契约

```python
class AgentResult(TypedDict):
    agent: str
    status: Literal["ok", "needs_confirmation", "blocked", "error"]
    reply: str                    # 给用户看/播报的自然语言
    payload: dict                 # 结构化数据（指标、用药、方案…）
    actions: list[dict]           # 给前端的动作
    evidence: list[dict]          # 证据来源（指南/知识图谱），支撑可追溯
    presentation: dict            # 结构化呈现（结论/要点/行动/边界/语音版），见 IO_SPEC
    trace: dict                   # 耗时、输入输出摘要
```

`actions` 类型：

```python
{"type": "record_created",   "record_id": 123, "summary": "已记录空腹血糖 6.8"}
{"type": "reminder_created", "reminder_id": 45, "summary": "已添加阿司匹林 每日1次"}
{"type": "navigate",         "target": "/medication"}
{"type": "toast",            "level": "success", "message": "已为您添加"}
```

原则：**写库由后端执行，页面只负责呈现与跳转**。

## 6. 记忆分层

采用「工作 / 情景 / 语义 / 知识」四层，全部落在现有 PG + pgvector + Redis 上，**不引入 Qdrant/Neo4j**。

| 记忆类型 | 存储位置 | 内容 | 生命周期 |
|---|---|---|---|
| 工作记忆 | Redis `patient_context` + ChatMessage | 当前会话上下文、待确认项 | 会话内，TTL 1h |
| 情景记忆 | AgentTrace + 会话历史 | 具体交互事件、异常记录 | 长期 |
| 语义记忆 | Patient 画像（疾病/过敏/用药/偏好） | 抽象事实与规则 | 长期 |
| 知识记忆 | KnowledgeChunk（pgvector） | 指南/疾病知识 | 长期 |

**关键机制**：

1. **巩固（Consolidate）**：会话结束时抽取「患者透露的新事实」（新症状、新用药、过敏、习惯），写回患者画像 / 语义记忆，实现跨会话「记得患者」。
2. **遗忘（Forget）**：按重要性 / 时间 / 容量裁剪记忆，控制上下文长度与成本（已有 20 会话上限，可再加重要性分级）。
3. **待确认状态**：`needs_confirmation` 时把 `{主题, 待写数据, TTL}` 写入工作记忆；用户回「确认」时协调器先查工作记忆再路由回原 agent。

## 7. 状态与中断

**要解决两个「边执行边等用户回答」的场景**：

- Safety 暂停（"要不要打 120"）
- 二次确认（"确认入库吗"）

**结论：不引入 LangGraph interrupt/checkpointer，用「外置会话状态 + 重放」实现。** 理由：

- 当前双链路（LangGraph 版 + 手写流式版）未统一，interrupt 要两边都接；
- `GraphState` 里有 `db`/`patient` 不可序列化对象，上 checkpointer 需先重构；
- 诊断的「多步追问」是**轮次驱动**，不是节点内暂停，外置状态同样覆盖。

**通用会话状态（Redis）**，一个机制覆盖三类：

```json
{"kind": "confirm_write", "agent": "monitor", "payload": {...}}
{"kind": "safety_120",    "original_message": "...", "original_intent": "consult"}
{"kind": "diagnosis_session", "stage": "collecting", "slots": {...}, "asked": [...]}
```

Key：`pending:{patient_id}:{session_id}`，TTL 5~10 分钟。

**消息处理流程**：

```
on_message(message):
  pending = redis.get(pending_key)

  if pending.kind == "confirm_write":
      confirm → 执行 payload 写库 → 清状态 → 返回 actions
      cancel  → 清状态 → 回复"已取消"
      other   → 清状态 → 正常路由

  if pending.kind == "safety_120":
      yes  → 走 SOS / 120
      no   → 记录 trace + 用 original_message 重放（跳过 Safety）
      other → 视为 no，继续

  if pending.kind == "diagnosis_session":
      → 交给 Diagnosis Agent 继续填槽 / 出结论

  正常路由...
```

**工程细节**：

1. **判断"是否在回应"**：先用规则（确认词：确认/好/是/对/可以；否定词：不/不用/取消/算了），识别不了就当新消息处理，不必为此多调一次 LLM；
2. **只保留一个 pending**：新 pending 覆盖旧的，避免状态错乱；
3. **Redis 不可用 → 降级为普通路由**：宁可让用户重说，也不能卡死。

**未来可选**：若诊断真出现「单次执行内必须暂停等人工」的需求，再评估上 LangGraph checkpointer；届时需先把 `db`/`patient` 移出 `GraphState`。

## 8. 上下文工程（GSSC 轻量版）

**目标**：每一轮不是把「历史 + RAG + 记录」硬拼进 prompt，而是按 token 预算做选择、按分区组织、超限有兜底。

**对照 GSSC 四阶段**：

| 阶段 | 本项目做法 |
|---|---|
| Gather | 汇集：系统指令、患者画像、近期记录、RAG 片段、会话历史 |
| Select | 综合分 = 相关性×0.7 + 新近性×0.3；低于阈值过滤；按 token 预算贪心填充 |
| Structure | 分区：`[Role]` / `[Patient Context]` / `[Evidence]` / `[History]` / `[Task]` / `[Output]` |
| Compress | 超限时按分区截断并标注，保留结构 |

**建议参数**：`max_tokens≈3000`、`reserve_ratio≈0.2`（给系统指令/免责声明/输出格式预留）、`relevance=0.7 / recency=0.3`。

**与记忆的关系**：记忆是「池子」，上下文工程是「每轮按预算从池子里舀一瓢」。

**轻量落地**（改 `build_consult_messages` / `build_planner_messages`）：

1. 加 token 预算（中文按 1 字≈1 token 估算）；
2. system prompt 改分区结构；
3. 历史按新近性加权，超限丢最老/最低分。

## 9. 诊断 Agent 与证据溯源

诊断 Agent 采用「单 Agent + 内部三步」的链路模板（借鉴 DeepRare 的分层思想，但不引入 HPO/OMIM/基因分析等罕见病组件）：

1. **表型抽取**：从对话抽 症状 / 体征 / 持续时间 / 诱因；
2. **知识匹配**：RAG 检索指南 + 复用现有 `Disease`/`Symptom` 知识图谱做「疾病-症状」匹配；
3. **证据融合**：按匹配度排序 → 输出「可能方向（排序）+ 依据 + 危险信号自查 + 就医建议」。

**证据溯源（evidence）**：每个 Agent 返回时附带结构化证据，前端与 `AgentTrace` 都可展示。

```python
evidence = [
    {"source": "中国高血压防治指南", "title": "血压控制目标", "snippet": "...", "score": 0.82},
    {"source": "知识图谱", "relation": "高血压 —has_symptom→ 头晕头痛"},
]
```

- 存进 `AgentResult.evidence` + `AgentTrace.output_data`；
- 前端展示「依据：…」，答辩可讲「每条建议可溯源到指南/图谱」；
- 诊断 Agent 的输出必须带 evidence，且强制免责声明。

## 10. 与现有代码的映射

| 动作 | 对象 |
|---|---|
| 保留并增强 | `router_agent`、`consult_agent`、`monitor_agent`、`planner_agent`、`document_agent` |
| 合并 | `warning_agent` → Consult |
| 删除 | `followup_agent`、`orchestrator.run_agent_graph`（无引用死代码） |
| 新增 | Safety、Medication、Diagnosis（阶段 3） |
| 修复 | `create_care_plan` 忽略 LLM 输出、用硬编码 |
| 收口 | 流式与非流式统一走同一张图 |

## 11. 评估与可观测性

**目标**：用数据证明 agent 有效，并能回归（改 prompt / 加 agent 后知道有没有变差）。

### 11.1 红旗识别测试集

- **样本**：60~100 句，三类——真急症 / 假警报（否定、历史、他人、假设）/ 普通咨询，人工标注；
- **指标**：**召回率（优先）**、精确率、混淆矩阵；
  - 医疗场景优先保召回：漏报可能致命，误报只是多问一句「要不要打 120」；
- **位置**：`backend/tests/eval/red_flag_cases.json`。

### 11.2 RAG 检索评估

- **样本**：20~30 个 query + ground truth（应命中的知识条目）；
- **指标**：Hit@3（top3 是否含正确条目）、MRR；
- **对比实验**：纯向量 vs 关键词降级 vs 加 MQE——用数据决定是否引入高级检索。

### 11.3 AgentTrace 可观测字段

现有：`agent_name / action / input_data / output_data / duration_ms`。建议补：

| 字段 | 用途 |
|---|---|
| `status` | ok / needs_confirmation / blocked / error |
| `evidence` | 引用来源，支撑可追溯 |
| `model` | 使用的模型（成本分析） |
| `tokens_in` / `tokens_out` | token 用量 |
| `fallback` | 是否走了 mock / 规则降级 |
| `error` | 异常信息 |

### 11.4 落地

```
backend/tests/eval/
├── red_flag_cases.json    # 红旗测试集
├── rag_queries.json       # query + ground truth
└── run_eval.py            # 批量跑分，输出召回/精确/Hit@3
```

- 先做「红旗 + RAG Hit@3」两项即可；
- 自写脚本，不引入 RAGAS / DeepEval；
- 评估结果可回归，作为改动的验收门槛。

## 12. 分阶段

- **阶段 1**：Safety + Router + Consult + Monitor + Planner + Document；指标抽取入库；动作层；记忆分层。
- **阶段 2**：Medication（药品库 + 安全审核 + 服药打卡）。
- **阶段 3**：Diagnosis（RAG 疾病知识库 + 初步诊断）。
