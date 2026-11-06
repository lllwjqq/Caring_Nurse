# OCR 前端实现提示词（交给前端模型）

> 背景：后端已完成 OCR 抽取/归档/诊断/复诊接口。你只改前端，不改后端 API 契约、不新增依赖。
> 遵循现有设计系统：`t-*` 字号、`--c-*` tokens、卡片圆角 24、触控 ≥48px、正文 ≥18px。

---

## 全局规则：所有面向用户的字段必须用中文 label

后端保留英文 canonical 值，同时返回 `*_label`。前端展示必须优先使用 label，**禁止**把 `blood_pressure`、`prescription`、`bid`、`high`、`warning` 等 raw code 直接显示给用户。

必须使用的中文字段：
- 文档：`doc_type_label`、`status_label`
- 指标：`record_type_label`、`context_label`、`abnormal_flag_label`、`unit_label`
- 用药：`frequency_label`、`route_label`、`dose_unit_label`、`timing_note_label`
- 警告：`severity_label`
- OCR：`ocr_meta.engine_label`、`is_mock_label`、`error_labels`、`page_type_labels`
- 诊断：`doc_type_label`、`status_label`
- 复诊：`status_label`
- 健康记录：`record_type_label`、`unit_label`
- 患者：`disease_labels`
- 预警：`level_label`、`source_label`

规则：
1. 有 `*_label` 时只用 label，不显示 raw code。
2. 编辑时提交 canonical 英文值（如 `frequency: "bid"`、`doc_type: "prescription"`），不要提交中文 label。
3. label 缺失时用前端兜底字典；再缺失显示「未知」/「其他」，不能空白。
4. 日期展示为「2026年10月8日」；数字保留原单位 label。
5. 所有页面（确认页、诊断时间线、复诊待办）统一遵守。

---

## 预警展示规则（本轮已修）

- 预警等级显示 `level_label`，来源显示 `source_label`，不得显示 `yellow`、`warning_agent` 等 raw code。
- 问诊页只展示 `is_read === false` 的预警气泡；点「已了解」调用 `markRead`，气泡立即隐藏。
- 不要在进入问诊页时自动把所有预警标记已读；否则用户还没点「已了解」，气泡就消失/无法交互。
- 预警历史页仍展示全部（含已读/已处理），供回看。
- 预警气泡/列表/历史三处统一使用 label。

---

## 提示词 1：确认页（优先做）

你现在负责「贴心小护士」的 OCR 确认页前端改造。后端接口已存在，不要改后端。

### 目标
1. 支持化验单、处方、出院小结、门诊病历四类确认与编辑。
2. 展示识别质量、低置信度、缺值、矛盾、混合单据、mock 标记。
3. 原文折叠且敏感信息默认打码；打码只做展示，不修改提交数据。
4. 确认后调用后端归档，展示动作结果。

### 后端契约（必须按此对接）

`GET /api/documents/{id}` 返回：
```ts
{
  id, patient_id, filename, doc_type, confidence,
  ocr_text: string | null,
  parsed_data: {
    doc_type: string,
    confidence: number | null,
    document_date: string | null,
    exam_date?: string | null,
    issue_date?: string | null,
    diagnoses: string[],
    metrics: Array<{
      name: string,
      record_type: string | null, // 仅 6 类核心有值
      value: number | null,
      unit: string,
      context?: string | null,
      systolic?: number | null,
      diastolic?: number | null,
      reference?: string | null,
      abnormal_flag?: string | null,
      confidence?: number | null,
      archiveable?: boolean
    }>,
    medications: Array<{
      name: string, generic_name?: string | null, spec?: string | null,
      dose?: number | null, dose_unit?: string | null,
      frequency?: string, route?: string | null,
      timing_note?: string | null, duration_days?: number | null,
      notes?: string | null, confidence?: number | null,
      archiveable?: boolean
    }>,
    followup_at?: string | null,
    followup_department?: string | null,
    family_history?: string | null,
    personal_history?: string | null,
    allergies?: string | null,
    warnings?: Array<{
      code: string,
      message: string,
      field: string | null,
      severity: 'info' | 'warning' | 'error'
    }>,
    needs_retake?: boolean,
    status?: string,
    ocr_meta?: {
      engine: string,
      is_mock: boolean,
      confidence: number | null,
      empty: boolean,
      errors: string[],
      page_count: number,
      page_types: string[]
    },
    mixed_documents?: boolean,
    multi_document_page?: boolean,
    modules?: Record<string, { label: string; items: string[] }>
  } | null,
  status: string, // awaiting_confirmation | needs_retake | confirmed | discarded
  created_at: string
}
```

> 后端还会在所有枚举旁返回中文 `*_label`（见顶部全局规则）。TypeScript 类型请加可选字段：
> `doc_type_label?`、`status_label?`、`record_type_label?`、`context_label?`、`abnormal_flag_label?`、`unit_label?`、`frequency_label?`、`route_label?`、`dose_unit_label?`、`timing_note_label?`、`severity_label?`。
> 页面展示只用 label；编辑提交仍用 raw 值。

确认接口：
```http
POST /api/documents/{id}/confirm
Content-Type: application/json
```
请求体所有字段可选；只传用户确认/编辑后的字段：
```ts
{
  metrics?: ParsedMetric[],
  exam_date?: string,
  medications?: ParsedMedication[],
  diagnoses?: string[],
  document_date?: string,
  followup_at?: string,
  followup_department?: string,
  family_history?: string,
  personal_history?: string
}
```
响应：
```ts
{
  document_id: number,
  status: 'confirmed',
  actions: Array<{
    type: 'record_created' | 'reminder_created' | 'diagnosis_created'
        | 'appointment_created' | 'patient_updated' | 'no_action',
    record_id?: number | null,
    reminder_id?: number | null,
    diagnosis_id?: number | null,
    appointment_id?: number | null,
    summary: string
  }>
}
```

放弃接口：`POST /api/documents/{id}/reject`。

### UI 要求
- `status === 'needs_retake'`：顶部红色/黄色提示「未识别到文字或质量过低，请重拍/换清晰图」；若没有任何可归档字段，禁用「确认入库」。
- `warnings` 按 `severity` 展示：`error` 红、`warning` 黄、`info` 灰；显示 `message`，可定位到对应字段。
- `ocr_meta.is_mock`：顶部固定横幅「演示 OCR 数据，请核对」。
- `mixed_documents` / `multi_document_page`：提示「含多种单据，建议分开上传；当前按最可能类型处理」。
- 低置信度（`confidence < 0.8`）：字段卡片标黄，文案「识别置信度较低，请核对」。
- 低置信度整份（`parsed_data.needs_retake`）：提示重拍，不自动归档。
- `metrics`：
  - 全部展示；
  - `record_type` 非空且 `archiveable === true` → 标「将写入健康记录」；
  - `record_type === null` → 标「仅展示，不入健康记录」；
  - 缺值/矛盾字段禁用或标红，不允许提交。
- `doc_type === 'prescription'`：展示/编辑 `document_date`、`diagnoses`、`medications`。
- `doc_type === 'discharge_summary' | 'outpatient_record'`：
  - 展示/编辑 `document_date`、`diagnoses`、`medications`；
  - 展示/编辑 `followup_at`、`followup_department`；
  - 展示/编辑 `family_history`、`personal_history`；
  - 展示 `modules` 8 模块（已有 `DocumentModulesView` 可复用）。
- 原文：
  - 放在「展开看原文」中；
  - 姓名、身份证、手机号默认打码；点「显示原文」可切换；
  - 不得把打码后的文本提交回后端；提交始终使用原始结构化字段。
- 确认按钮文案「确认入库」；确认后展示 actions 列表，提供「返回录入」。
- 放弃按钮二次确认（可选简单确认弹窗）。
- 不要新增 npm 依赖。

### 打码规则（展示层）
- 姓名：`张**`/`李**`（保留首字）；
- 身份证：`110***********1234`（保留前 3 后 4）；
- 手机号：`138****8000`（保留前 3 后 4）；
- 仅处理 `ocr_text` 展示；`parsed_data` 原样提交。

### 交付
- 改 `frontend/src/pages/DocumentConfirmPage.tsx`、`frontend/src/components/DocumentConfirmForm.tsx`、`frontend/src/lib/types.ts`、`frontend/src/api/client.ts`。
- 运行 `npm run build` 通过。
- 不要改后端。

---

## 提示词 2：诊断时间线（健康档案页）

在「我的 > 健康档案」页面增加「诊断记录」时间线。

### 后端契约
`GET /api/diagnoses`：
```ts
Array<{
  id: number,
  patient_id: number,
  name: string,
  diagnosed_at: string | null, // ISO
  doc_type: string, // discharge_summary/outpatient_record/prescription/manual
  doc_type_label: string,
  source_document_id: number | null,
  status: 'current' | 'past',
  status_label: string,
  notes: string | null,
  created_at: string
}>
```
无分页。按 `diagnosed_at ?? created_at` 倒序展示。

### UI
- 位置：`frontend/src/pages/SubPages/HealthProfilePage.tsx` 表单下方，新增「诊断记录」卡片。
- 每条：诊断名（`t-h2`）、日期（`t-cap text-ink-soft`）、来源标签用 `doc_type_label`、状态标签用 `status_label`。
- 空状态：「暂无诊断记录，上传病历或处方后会自动归档」。
- 点击来源文档：若有 `source_document_id`，跳转 `/record/document/{id}`；无则不可点。
- 触控 ≥48px；不要新增依赖。

### 交付
- 改 `HealthProfilePage.tsx`、`lib/types.ts`、`api/client.ts`。
- `npm run build` 通过。

---

## 提示词 3：复诊待办（监测页）

在「监测」页增加「近期待办」区块。

### 后端契约
`GET /api/appointments?status=pending`：
```ts
Array<{
  id: number,
  patient_id: number,
  title: string,
  department: string | null,
  due_at: string, // ISO
  source_document_id: number | null,
  status: 'pending' | 'done' | 'cancelled',
  status_label: string,
  created_at: string
}>
```
更新状态：
```http
PATCH /api/appointments/{id}
{ "status": "done" | "cancelled" }
```

### UI
- 位置：`frontend/src/pages/MonitorPage.tsx` 顶部 `RiskCard` 之后、「今日指标」之前。
- 标题「近期待办」；每条显示 `department + title`、`due_at`（月日 + 时间）、来源；状态使用 `status_label`。
- 按钮：「完成了」→ PATCH done；「取消」→ PATCH cancelled；操作后从列表移除/刷新。
- 空状态不显示区块或显示「暂无复诊安排」。
- 触控 ≥48px；不要新增依赖。

### 交付
- 改 `MonitorPage.tsx`、`lib/types.ts`、`api/client.ts`。
- `npm run build` 通过。

---

## 提示词 4：聊天粘贴病历的确认提示

后端已把聊天粘贴病历改为 `status='needs_confirmation'`：
- `reply` 是 8 模块解释 + 「回复确认归档 / 取消」；
- `presentation.action_items` 包含确认/取消；
- `actions` 在确认后才返回 `diagnosis_created` / `appointment_created` / `reminder_created`；
- **不会**返回原始文本。

前端要求：
- 不要展示原始 OCR/聊天原文（后端没有返回）；
- 沿用现有 pending 文本确认流程（用户输入「确认」/「取消」）；
- 若已有通用 `PresentationView`，正常渲染 `summary/key_points/action_items`；
- 不新增确认按钮也可以；如需按钮，点击后发送 `{ message: '确认', session_id }` 或 `{ message: '取消', session_id }`。

---

## 提示词 5：类型与 API 客户端（可合并到以上任务）

更新 `frontend/src/lib/types.ts`：
```ts
export interface DiagnosisItem {
  id: number; patient_id: number; name: string;
  diagnosed_at: string | null; doc_type: string;
  source_document_id: number | null;
  status: 'current' | 'past'; notes: string | null; created_at: string;
}
export interface AppointmentItem {
  id: number; patient_id: number; title: string;
  department: string | null; due_at: string;
  source_document_id: number | null;
  status: 'pending' | 'done' | 'cancelled'; created_at: string;
}
```
并扩展 `ParsedDocumentData`：
```ts
document_date?: string | null;
diagnoses?: string[];
followup_at?: string | null;
followup_department?: string | null;
family_history?: string | null;
personal_history?: string | null;
warnings?: Array<{code:string;message:string;field:string|null;severity:'info'|'warning'|'error'}>;
needs_retake?: boolean;
status?: string;
ocr_meta?: {engine:string;is_mock:boolean;confidence:number|null;empty:boolean;errors:string[];page_count:number;page_types:string[]};
mixed_documents?: boolean;
multi_document_page?: boolean;
```
`ParsedMetric` 增加 `archiveable?: boolean`；`HealthRecordItem` 增加 `source_document_id?: number | null`。

`frontend/src/api/client.ts`：
```ts
export const diagnosisApi = {
  list: () => api.get('/diagnoses'),
}
export const appointmentApi = {
  list: (status = 'pending') => api.get('/appointments', { params: { status } }),
  update: (id: number, status: 'done' | 'cancelled') =>
    api.patch(`/appointments/${id}`, { status }),
}
```
`confirmDocument` 的 data 类型扩展上述可选字段。

---

## 全局约束
- 不改后端 API、不加依赖、不引入新状态库。
- 不把打码文本写回数据库。
- 所有触控 ≥48px，正文 ≥18px。
- 构建必须 `npm run build` 通过。
