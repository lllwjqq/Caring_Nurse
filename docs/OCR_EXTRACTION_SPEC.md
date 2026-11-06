# OCR 抽取规格（OCR Extraction Spec）

> 定位：定义「从 OCR 文本中提取哪些关键信息、落到系统哪里、异常时怎么处理」。
> 边界：本文只定义信息规格与业务规则，不规定具体技术实现（LLM / 正则 / OCR 引擎选型）。

## 一、总体原则

1. **跨单据统一字段词表**：诊断、用药、指标、医嘱等字段在各单据中复用同一套定义与结构，缺的留空。
2. **一律先确认、后入库**：任何抽取结果都先给用户确认，确认后才写库。
3. **抽取与解释分离**：抽取只负责结构化，解释与归档分开处理（见第二节现状架构）。
4. **不臆造**：抽不到就留空或标记，禁止编造数值、药名、日期。

## 二、现状架构（改前先理解）

- 抽取：`backend/app/services/document_parser.py`（分类 + 按类型抽取 + 正则兜底）
- 归档：`backend/app/services/document_processing.py` 的 `dispatch`
- 解释：`backend/app/graph/orchestrator.py` 的 `document_agent`（聊天粘贴病历）
- OCR：`backend/app/services/ocr_service.py`

## 三、文档类型与抽取字段

| 文档类型 | 必抽字段 | 说明 |
|---|---|---|
| 化验单 lab_report | 检测日期、指标列表（名称/值/单位/参考范围/异常标记） | 全部指标都抽；仅 6 类核心指标入库，其余仅展示 |
| 处方 prescription | 开方日期、药品列表（药名/规格/剂量/频次/疗程）、诊断 | 诊断用于解释「为什么开这个药」 |
| 出院小结 discharge_summary | 诊断、主诉、关键异常、用药、医嘱、复诊时间 | 复诊时间用于生成复诊提醒 |
| 门诊病历 outpatient_record | 诊断、主诉、用药、医嘱、随访 | 与出院小结共用同一套字段定义 |
| 药品说明书 drug_insert | 不抽取 | 本版不做 |
| 其他 other | 不抽取 | — |

核心 6 类指标：血压、血糖、体重、血脂、血氧、心率。

## 四、字段 → 系统映射

| 抽取字段 | 归宿 |
|---|---|
| 指标（6 类） | `HealthRecord` |
| 指标（其余） | `MedicalDocument.parsed_data`，仅展示 |
| 用药 | `MedicationReminder` |
| 检测 / 开方日期 | `HealthRecord.recorded_at` / `MedicationReminder.start_date` |
| 过敏 | `Patient.allergies` |
| 既往史 / 家族史 | `Patient.health_profile`（JSONB） |
| 诊断 | 新建 `Diagnosis` 表 |
| 复诊时间 | 新建 `Appointment` 表（并生成复诊提醒） |
| 医嘱 | `parsed_data` + 解释展示 |
| 危险信号 | `parsed_data`（可选生成预警） |
| 医院 / 科室 / 医生 / 主诉 | `parsed_data` |
| 溯源 | `HealthRecord` 补 `source_document_id` |

### 4.1 新增表：Diagnosis（诊断记录）

| 字段 | 说明 |
|---|---|
| patient_id | 归属患者 |
| name | 诊断名称（自由文本，如「腔隙性脑梗死」） |
| diagnosed_at | 诊断日期（取出院 / 门诊日期，缺则空） |
| doc_type | 来源（出院小结 / 门诊病历 / 处方 / 手动） |
| source_document_id | 关联文档（聊天粘贴可为空） |
| status | 当前 / 既往 |
| notes | 备注 |

### 4.2 新增表：Appointment（就诊 / 复诊安排）

| 字段 | 说明 |
|---|---|
| patient_id | 归属患者 |
| title | 如「神经内科复诊」 |
| department | 科室（可空） |
| due_at | 复诊时间 |
| source_document_id | 关联文档 |
| status | pending / done / cancelled |

### 4.3 展示位置

- 诊断记录：我的 > 健康档案 > 诊断记录（时间线）
- 复诊安排：监测页「近期待办」+ 我的可见

### 4.4 提醒时机

复诊**提前 3 天 + 当天**各提醒一次。

## 五、不确定性规则

| 场景 | 处理 |
|---|---|
| 置信度 < 0.8 | 标黄、需用户确认 |
| 整份 confidence < 0.5 | 提示重拍 |
| 缺关键值（数值 / 药名） | 不归档，标「待补充」 |
| 缺非关键（参考范围 / 科室） | 留空 |
| 数值矛盾（如收缩压 < 舒张压） | 不入库 + 高亮提示核对 |
| OCR 空 / 乱码 | 提示「未识别到文字，请重拍或换清晰图」 |
| 一份文档无可用字段 | 提示「未识别到可归档信息」 |
| 多页 PDF | 合并处理；若含多种单据，提示分开上传 |
| 一页多单 | 按最可能类型处理，提示拆分 |

## 六、原文保留与展示

- 保留原文（`MedicalDocument.ocr_text`）；
- 主视图大白话，原文折叠可展开；
- 敏感信息（姓名 / 身份证 / 电话）展示时默认打码，可点开；
- **存原文、展示脱敏**（脱敏只做展示层）；
- 派生数据带 `source_document_id` 溯源；
- 删除文档：默认**保留**已归档记录，可勾选「同时删除关联指标 / 用药 / 诊断」。

### 6.1 展示层中文化（新增约定）

- **canonical 值保持英文**：`doc_type`、`record_type`、`frequency`、`context`、`abnormal_flag`、`status`、`severity` 等继续使用英文码值，作为 API/数据库契约。
- **所有面向用户的展示必须使用中文 label**：前端不得直接渲染 `blood_pressure`、`prescription`、`bid`、`high`、`warning` 等 raw code。
- 后端在文档、指标、用药、诊断、复诊、预警等响应中提供 `*_label`：
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
- **编辑回传仍使用 canonical 英文值**：例如用户看到「每日2次」，提交仍是 `frequency: "bid"`；用户看到「处方」，提交仍是 `doc_type: "prescription"`。
- **未知枚举**：显示「未知」或「其他」，不得空白；不得把未知中文回写成 canonical。
- **单位**：`mg/g/ml/mmHg/mmol/L` 等提供中文 `unit_label`（毫克/克/毫升/毫米汞柱/毫摩尔每升）；前端可中文展示，但编辑仍回传原始单位。
- **日期/数字**：展示层格式化为「2026年10月8日」「140/90 mmHg」等中文习惯；不改变 API 存储值。

**主要映射表**

| canonical | 中文 label |
|---|---|
| `lab_report` / `prescription` / `discharge_summary` / `outpatient_record` / `drug_insert` / `other` | 化验单 / 处方 / 出院小结 / 门诊病历 / 药品说明书 / 其他文书 |
| `awaiting_confirmation` / `needs_retake` / `confirmed` / `discarded` | 待确认 / 需要重拍 / 已归档 / 已放弃 |
| `blood_glucose` / `blood_pressure` / `heart_rate` / `spo2` / `blood_lipid` / `weight` | 血糖 / 血压 / 心率 / 血氧 / 血脂 / 体重 |
| `fasting` / `postprandial` / `random` / `bedtime` | 空腹 / 餐后2小时 / 随机 / 睡前 |
| `ldl` / `tc` / `tg` / `hdl` | 低密度脂蛋白 / 总胆固醇 / 甘油三酯 / 高密度脂蛋白 |
| `qd` / `bid` / `tid` / `qid` / `q8h` / `qn` / `prn` | 每日1次 / 每日2次 / 每日3次 / 每日4次 / 每8小时 / 睡前 / 按需 |
| `high` / `low` | 偏高 / 偏低 |
| `current` / `past` | 当前 / 既往 |
| `pending` / `done` / `cancelled` | 待复诊 / 已完成 / 已取消 |
| `info` / `warning` / `error` | 提示 / 警告 / 错误 |

---

## 七、验收（轻量）

- 演示样本（每类约 2 份，共约 8 份）端到端全过；
- bad case 清单收敛；
- 降级不崩：无 LLM Key / 无 OCR 引擎 / 低质量图片，均优雅提示、不产生错误数据；
- 待样本扩充到每类 5 份以上后，再补分类准确率、字段召回率等统计标准。

## 八、改动前基线

改 OCR 前先跑一遍现有 8 份样本，记录 baseline（抽对 / 抽错），用于对比迭代效果。
