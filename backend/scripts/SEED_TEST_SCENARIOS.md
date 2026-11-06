# 测试数据场景 → 预期结果对照表

对应脚本：[`seed_test_data.py`](seed_test_data.py)
样本目录：[`backend/knowledge/samples/`](../knowledge/samples/)

## 运行

```bash
cd backend
python scripts/seed_test_data.py
# Docker:
docker compose exec backend python scripts/seed_test_data.py
```

- 测试账号统一密码：`test123456`
- 账号命名空间：`test.<slug>@nurse.com`
- 幂等：每次先删除这 14 个测试账号及其患者数据，再重新生成；**不会修改 `demo@nurse.com`**
- 若 `DATABASE_URL` 指向非本地/容器内主机，脚本默认拒绝执行；确认非生产库时追加 `--force`
- 脚本会幂等补齐旧库缺失的 `medical_documents.confidence` 列（`create_all` 不会给已有表补列）

## 一、阈值口径（来自 `alert_service.DEFAULT_THRESHOLDS`）

| 指标 | metric_key | yellow | orange | red |
|---|---|---|---|---|
| 血糖 | `fasting` | ≥7.0 | ≥10.0 | ≥13.9 |
| 血糖 | `postprandial` | ≥10.0 | ≥13.9 | ≥16.7 |
| 血糖 | `random` | ≥11.1 | ≥13.9 | ≥16.7 |
| 血糖 | `bedtime` | ≥8.0 | ≥10.0 | ≥13.9 |
| 血糖 | `value`（无 context） | ≥7.0 | ≥11.1 | ≥16.7 |
| 收缩压 | `systolic` | ≥140 | ≥160 | ≥180 |
| 舒张压 | `diastolic` | ≥90 | ≥100 | ≥110 |
| 血脂 LDL-C | `ldl` | ≥3.4 | ≥4.1 | ≥4.9 |
| 血氧 | `value` | ≤94 | ≤90 | ≤85 |
| 心率 / 体重 | — | 无阈值 | 无阈值 | 无阈值 |

> 说明：`AlertService.check_threshold` 对血压只取 `extra_data.systolic` 与 `systolic` 阈值行，**舒张压阈值行会被跳过**；血脂必须带 `extra_data.type=ldl` 才会命中 `ldl` 阈值行。

## 二、账号与场景总览

| 账号 | 慢病 | 记录数 | 异常数 | 预警分布 | 用途 |
|---|---|---|---|---|---|
| `test.single.diabetes@nurse.com` | 糖尿病 | 4 | 3 | yellow 1 / orange 1 / red 1 | 空腹血糖边界 |
| `test.single.hypertension@nurse.com` | 高血压 | 4 | 3 | yellow 1 / orange 1 / red 1 | 收缩压边界 |
| `test.bp.diastolic@nurse.com` | 高血压 | 1 | 0 | — | 舒张压口径（预期不告警） |
| `test.single.hyperlipidemia@nurse.com` | 高血脂 | 4 | 3 | yellow 1 / orange 1 / red 1 | LDL-C 边界 |
| `test.lipid.nocontext@nurse.com` | 高血脂 | 1 | 0 | — | 血脂无 context（预期不告警） |
| `test.single.copd@nurse.com` | 慢阻肺 | 4 | 3 | yellow 1 / orange 1 / red 1 | 血氧 min 边界 |
| `test.multi@nurse.com` | 四病共存 | 4 | 4 | yellow 1 / orange 2 / red 1 | 多病 + 方案 + 生活方式 |
| `test.trend7@nurse.com` | 糖尿病+高血压 | 14 | 4 | —（不建 Alert） | 7 天趋势 |
| `test.trend30@nurse.com` | 糖尿病+高血压+高血脂 | 50 | 10 | —（不建 Alert） | 30 天趋势 |
| `test.empty@nurse.com` | 无 | 0 | 0 | — | 空数据状态 |
| `test.med.freq@nurse.com` | 高血压+糖尿病 | 0 | 0 | — | 用药各频次 + 打卡 |
| `test.med.safety@nurse.com` | 高血压+高血脂 | 0 | 0 | — | 过敏冲突 + 相互作用 |
| `test.med.safety2@nurse.com` | 高血脂+高血压 | 0 | 0 | — | 相互作用 + 剂量 + 重复 |
| `test.documents@nurse.com` | 四病共存 | 0 | 0 | — | 4 类医疗文档 |

## 三、指标记录 → 预警等级

> 预警由 `check_threshold` 的规则等级直接落库；`extra_data.ml_score` 固定为 `0.0`，不套用 `evaluate_record` 的 ML 提级，因此等级可精确断言。

### 1. 单病-糖尿病（空腹血糖）

| 记录 | 值（mmol/L） | 预期 `is_abnormal` | 预期 Alert |
|---|---|---|---|
| 空腹血糖 | 6.9 | false | — |
| 空腹血糖 | 7.0 | true | yellow |
| 空腹血糖 | 10.0 | true | orange |
| 空腹血糖 | 13.9 | true | red |

### 2. 单病-高血压（收缩压）

| 记录 | 值（mmHg） | 预期 `is_abnormal` | 预期 Alert |
|---|---|---|---|
| 血压 | 139/85 | false | — |
| 血压 | 140/90 | true | yellow |
| 血压 | 160/100 | true | orange |
| 血压 | 180/110 | true | red |

### 3. 舒张压口径

| 记录 | 值（mmHg） | 预期 `is_abnormal` | 预期 Alert | 说明 |
|---|---|---|---|---|
| 血压 | 130/105 | false | — | 当前只评估收缩压，舒张压 105 不触发 |

### 4. 单病-高血脂（LDL-C）

| 记录 | 值（mmol/L） | 预期 `is_abnormal` | 预期 Alert |
|---|---|---|---|
| 血脂 `type=ldl` | 3.3 | false | — |
| 血脂 `type=ldl` | 3.4 | true | yellow |
| 血脂 `type=ldl` | 4.1 | true | orange |
| 血脂 `type=ldl` | 4.9 | true | red |

### 5. 血脂无 context

| 记录 | 值（mmol/L） | 预期 `is_abnormal` | 预期 Alert | 说明 |
|---|---|---|---|---|
| 血脂（无 `type`） | 5.0 | false | — | 未命中 `ldl` 阈值行 |

### 6. 单病-慢阻肺（血氧）

| 记录 | 值（%） | 预期 `is_abnormal` | 预期 Alert |
|---|---|---|---|
| 血氧 | 95 | false | — |
| 血氧 | 94 | true | yellow |
| 血氧 | 90 | true | orange |
| 血氧 | 85 | true | red |

### 7. 多病共存

| 记录 | 值 | 预期 Alert |
|---|---|---|
| 空腹血糖 | 8.0 mmol/L | yellow |
| 血压 | 165/95 mmHg | orange |
| 血脂 `type=ldl` | 5.0 mmol/L | red |
| 血氧 | 88 % | orange |

### 8. 7 天趋势（14 条，4 条异常，0 条 Alert）

- 血糖（空腹，7 天）：`6.2, 6.5, 6.8, 7.0, 7.4, 6.6, 6.9` → `7.0`、`7.4` 为 yellow，共 2 条异常
- 血压（7 天）：`128/82, 132/84, 138/86, 142/88, 145/90, 136/85, 130/83` → `142`、`145` 为 yellow，共 2 条异常

### 9. 30 天趋势（50 条，10 条异常，0 条 Alert）

- 血糖（30 天）：28 条正常 + `7.1`、`7.3` 两条 yellow → 2 条异常
- 血压（每 3 天 1 条，共 10 条）：`142`、`145`、`140`、`150` 四条 yellow → 4 条异常
- 血脂 LDL（每 3 天 1 条，共 10 条）：`3.5`、`3.6`、`3.4`、`3.7` 四条 yellow → 4 条异常

## 四、医疗文档 → 预期识别类型

脚本对每份样本断言：长度 ≥80、命中 ≥2 个 `DOCUMENT_MARKERS`、关键词分类等于预期类型。

| 样本文件 | 长度 | 标记词命中 | 预期 `doc_type` | 关键解析字段 |
|---|---|---|---|---|
| `化验单-样本4.txt` | 426 | 2 | `lab_report` | `exam_date=2026-10-08`；空腹血糖 8.0、餐后 14.5、血压 165/100、心率 78、血氧 88、TC 5.8、TG 2.1、LDL 4.2、HDL 1.0、体重 70 |
| `处方-样本5.txt` | 269 | 2 | `prescription` | `issue_date=2026-10-08`；阿莫西林 500mg bid、辛伐他汀 20mg qn、克拉霉素 250mg bid、二甲双胍 500mg bid |
| `出院小结-样本6.txt` | 459 | 11 | `discharge_summary` | 诊断：2型糖尿病/高血压3级/高脂血症；关键异常、出院带药、出院医嘱、口语化摘要 |
| `门诊病历-样本7.txt` | 287 | 6 | `outpatient_record` | 诊断：2型糖尿病/高血压2级；主诉、现病史、既往史、体格检查、治疗方案 |

### 文档确认后的预期（手工点「确认入库」时）

- **化验单**（`test.documents`，四病共存）：
  - 空腹血糖 8.0 → yellow；餐后 14.5 → orange；血压 165 → orange；血氧 88 → orange；LDL 4.2 → orange
  - 心率 78、体重 70、TC/TG/HDL → 无阈值，不告警
  - 说明：确认走 `DocumentService.dispatch → evaluate_record`，需要 Redis 推送；脚本本身不依赖 Redis
- **处方**（`test.documents` 已有 allergies=青霉素、medications=华法林）：
  - 生成 4 条服药提醒；用药安全页预期出现 2 条 red：阿莫西林过敏、辛伐他汀+克拉霉素相互作用
- **出院小结 / 门诊病历**：`dispatch` 返回 `no_action`，仅保存识别原文与结构化结果

## 五、用药频次

| 药品 | 频次 | timing_note | 预期 `times_of_day` |
|---|---|---|---|
| 氨氯地平片 | qd | — | `["08:00"]` |
| 二甲双胍片 | bid | — | `["08:00","20:00"]` |
| 阿司匹林肠溶片 | tid | — | `["08:00","12:30","18:30"]` |
| 硝苯地平控释片 | qid | — | `["08:00","12:30","18:00","22:00"]` |
| 缬沙坦胶囊 | q8h | — | `["08:00","16:00","00:00"]` |
| 瑞舒伐他汀片 | qn | — | `["21:00"]` |
| 奥美拉唑肠溶胶囊 | prn | — | `[]` |
| 甲钴胺片 | qd | 晨起 | `["07:30"]` |
| 阿托伐他汀片 | bid | 睡前 | `["21:00"]`（睡前覆盖频次默认时点） |

今日打卡：氨氯地平 `08:00`=`taken`；二甲双胍 `20:00`=`skipped`。

## 六、用药安全（`GET /api/medication/safety`）

### `test.med.safety@nurse.com`

- 输入：`allergies=青霉素`、`medications=华法林 2.5mg qd`；提醒：阿莫西林 500mg qd、阿司匹林 100mg qd
- 预期 2 条 **red**：
  1. 过敏风险：阿莫西林（青霉素交叉过敏）
  2. 可能相互作用：阿司匹林 + 华法林

### `test.med.safety2@nurse.com`

- 提醒：辛伐他汀 100mg qd、克拉霉素 250mg bid、瑞舒伐他汀 10mg qd、红霉素 250mg tid、二甲双胍片 500mg bid、二甲双胍缓释片 500mg qd
- 预期 4 条：
  1. **red**：辛伐他汀 + 克拉霉素（major）
  2. **orange**：瑞舒伐他汀 + 红霉素（moderate）
  3. **orange**：剂量偏高：辛伐他汀（100mg > 上限 80mg）
  4. **orange**：重复用药：二甲双胍（普通片 + 缓释片同成分）

### `test.med.freq@nurse.com`

- 预期 0 条安全问题（用于验证频次不应误报安全项）

## 七、已知口径与坑（以代码为准）

1. **舒张压不参与告警**：`check_threshold` 对血压只评估收缩压；`130/105` 用例预期正常。
2. **血脂必须带 context**：`blood_lipid` 只有 `extra_data.type=ldl` 才命中 `ldl` 阈值行；否则即使 5.0 也不告警。
3. **心率/体重无阈值**：两类记录永远 `is_abnormal=false`，不会产生预警。
4. **ML 提级未用于种子预警**：`evaluate_record` 在 `ml_score>0.7` 时会把 yellow/None 提到 orange；脚本直接落规则等级并把 `ml_score` 固定为 0，保证可断言。若通过 API 继续给异常记录很多的患者录入，仍可能触发 ML 提级。
5. **文档分类的确定性口径**：脚本用 `_classify_keywords`（关键词兜底）断言；配置 `LLM_API_KEY` 时线上 `classify_document` 可能走 LLM，以线上结果为准。四份样本都刻意命中了强关键词。
6. **随访已停用**：`tasks/scheduler.py` 不再注册 `create_followup_tasks`，`/follow-ups` 接口标记 deprecated；本脚本不生成随访任务。
7. **文档状态用 `uploaded`**：`medical_documents.status` 实际为 `VARCHAR(20)`，而 `awaiting_confirmation` 有 21 个字符；脚本使用 `uploaded`（前端显示「待处理」，仍可被 `/documents/{id}/confirm` 确认）。这是当前模型长度与取值不一致的兼容处理。
8. **时间戳是相对执行时刻的**：趋势记录以 `now - N days` 生成，保证趋势窗口始终有数据；指标数值与预警等级不受运行时间影响。
9. **旧库补列**：本地库若缺 `medical_documents.confidence`，脚本会在 `create_all` 后执行一次 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`；不修改任何业务代码。
10. **幂等性**：重复执行会先删后建，账号 ID / 记录 ID 会变化，但账号集合、数值、异常标记与预警等级保持一致。

## 八、快速核对 SQL

```sql
-- 1) 测试账号（应为 14 个，且 demo@nurse.com 仍存在）
select email from users where email like 'test.%@nurse.com' order by email;
select email from users where email = 'demo@nurse.com';

-- 2) 记录与预警等级
select u.email, r.record_type, r.value, r.extra_data, r.is_abnormal, a.level
from health_records r
join patients p on p.id = r.patient_id
join users u on u.id = p.user_id
left join alerts a
  on a.patient_id = p.id and (a.extra_data->>'record_id')::int = r.id
where u.email like 'test.%@nurse.com'
order by u.email, r.recorded_at;

-- 3) 用药频次
select u.email, m.medication_name, m.frequency, m.times_of_day
from medication_reminders m
join patients p on p.id = m.patient_id
join users u on u.id = p.user_id
where u.email like 'test.med.%@nurse.com'
order by u.email, m.medication_name;

-- 4) 文档
select u.email, d.filename, d.doc_type, d.status
from medical_documents d
join patients p on p.id = d.patient_id
join users u on u.id = p.user_id
where u.email = 'test.documents@nurse.com'
order by d.filename;
```
