/**
 * 语音文本 → 健康参数/用药 规则解析（规格 §7.1）。
 *
 * 后端只有 ASR，无「文本→指标」接口（§1.3 缺口），因此前端做确定性规则解析。
 * 解析失败返回 null，由调用方提示「没太听清，能再说一次吗？」。
 */
import { RECORD_TYPE_LABELS } from '../constants/healthRecords'

export interface MetricDraft {
  kind: 'metric'
  record_type: string
  value: number
  unit: string
  extra_data: Record<string, unknown>
  /** 用于确认卡的人话，如「空腹血糖 6.8 mmol/L」 */
  label: string
  /** 原始识别文本 */
  raw: string
}

export interface MedicationDraft {
  kind: 'medication'
  medication_name: string
  dose?: number
  dose_unit?: string
  frequency?: string
  label: string
  raw: string
}

export type HealthDraft = MetricDraft | MedicationDraft

const GLUCOSE_CONTEXTS: Array<{ key: string; words: string[] }> = [
  { key: 'fasting', words: ['空腹'] },
  { key: 'postprandial', words: ['餐后', '饭后', '两小时', '2小时'] },
  { key: 'random', words: ['随机'] },
  { key: 'bedtime', words: ['睡前'] },
]

const LIPID_CONTEXTS: Array<{ key: string; words: string[] }> = [
  { key: 'ldl', words: ['低密度', 'LDL'] },
  { key: 'tc', words: ['总胆固醇', '胆固醇'] },
  { key: 'tg', words: ['甘油三酯'] },
  { key: 'hdl', words: ['高密度', 'HDL'] },
]

const FREQ_WORDS: Array<{ key: string; words: string[] }> = [
  { key: 'qd', words: ['每天一次', '每日一次', '一日一次', '一天一次', '每天1次', '每日1次', '一日1次', '一天1次', 'qd'] },
  { key: 'bid', words: ['每天两次', '每日两次', '一日两次', '一天两次', '每天2次', '每日2次', '一日2次', '一天2次', '早晚', 'bid'] },
  { key: 'tid', words: ['每天三次', '每日三次', '一日三次', '一天三次', '每天3次', '每日3次', '一日3次', '一天3次', '早中晚', 'tid'] },
  { key: 'qid', words: ['每天四次', '每日四次', '一日四次', '一天四次', '每天4次', '每日4次', '一日4次', '一天4次', 'qid'] },
  { key: 'qn', words: ['睡前', 'qn'] },
]

function findNumber(text: string): number | null {
  const m = text.match(/(\d+(?:\.\d+)?)/)
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) ? n : null
}

function inRange(n: number | null, min: number, max: number): n is number {
  return n != null && n >= min && n <= max
}

function pickContext(text: string, table: Array<{ key: string; words: string[] }>): string | null {
  for (const row of table) {
    if (row.words.some((w) => text.includes(w))) return row.key
  }
  return null
}

function metric(
  text: string,
  recordType: string,
  value: number,
  unit: string,
  extraData: Record<string, unknown> = {},
  nameOverride?: string,
): MetricDraft {
  const name = nameOverride || RECORD_TYPE_LABELS[recordType] || recordType
  const ctxLabel = extraData.type
    ? GLUCOSE_LABELS[String(extraData.type)] || ''
    : ''
  const sys = Number(extraData.systolic)
  const dia = Number(extraData.diastolic)
  const valueLabel =
    recordType === 'blood_pressure' && Number.isFinite(sys) && Number.isFinite(dia)
      ? `${sys}/${dia}`
      : String(value)
  return {
    kind: 'metric',
    record_type: recordType,
    value,
    unit,
    extra_data: extraData,
    label: `${ctxLabel}${name} ${valueLabel} ${unit}`,
    raw: text,
  }
}

const GLUCOSE_LABELS: Record<string, string> = {
  fasting: '空腹',
  postprandial: '餐后2h',
  random: '随机',
  bedtime: '睡前',
}

const LIPID_LABELS: Record<string, string> = {
  ldl: '低密度脂蛋白',
  tc: '总胆固醇',
  tg: '甘油三酯',
  hdl: '高密度脂蛋白',
}

function parseBloodGlucose(text: string): MetricDraft | null {
  if (!text.includes('血糖')) return null
  const value = findNumber(text)
  if (!inRange(value, 1, 33)) return null
  const ctx = pickContext(text, GLUCOSE_CONTEXTS)
  return metric(text, 'blood_glucose', value, 'mmol/L', ctx ? { type: ctx } : {})
}

function parseBloodPressure(text: string): MetricDraft | null {
  if (!/(血压|高压|低压)/.test(text)) return null
  let systolic: number | null = null
  let diastolic: number | null = null

  const slash = text.match(/(\d{2,3})\s*[/／,，、]\s*(\d{2,3})/) ||
    text.match(/(\d{2,3})\s+(\d{2,3})/)
  if (slash) {
    systolic = Number(slash[1])
    diastolic = Number(slash[2])
  } else {
    const sysMatch = text.match(/(?:高压|收缩压)\s*(\d{2,3})/)
    const diaMatch = text.match(/(?:低压|舒张压)\s*(\d{2,3})/)
    if (sysMatch) systolic = Number(sysMatch[1])
    if (diaMatch) diastolic = Number(diaMatch[1])
  }

  if (!inRange(systolic, 40, 300) || !inRange(diastolic, 40, 300)) return null
  return metric(
    text,
    'blood_pressure',
    systolic,
    'mmHg',
    { systolic, diastolic },
    '血压',
  )
}

function parseWeight(text: string): MetricDraft | null {
  if (!text.includes('体重')) return null
  const value = findNumber(text)
  if (!inRange(value, 10, 500)) return null
  return metric(text, 'weight', value, 'kg')
}

function parseHeartRate(text: string): MetricDraft | null {
  if (!/(心率|脉搏)/.test(text)) return null
  const value = findNumber(text)
  if (!inRange(value, 30, 220)) return null
  return metric(text, 'heart_rate', value, '次/分')
}

function parseSpo2(text: string): MetricDraft | null {
  if (!/(血氧|血氧饱和度)/.test(text)) return null
  const value = findNumber(text)
  if (!inRange(value, 50, 100)) return null
  return metric(text, 'spo2', value, '%')
}

function parseBloodLipid(text: string): MetricDraft | null {
  if (!/(低密度|总胆固醇|胆固醇|甘油三酯|高密度|血脂)/.test(text)) return null
  const value = findNumber(text)
  if (!inRange(value, 0.1, 30)) return null
  const ctx = pickContext(text, LIPID_CONTEXTS)
  return metric(text, 'blood_lipid', value, 'mmol/L', ctx ? { type: ctx } : {}, ctx ? LIPID_LABELS[ctx] : undefined)
}

function parseMedication(text: string): MedicationDraft | null {
  // 触发词 + 药名（以常见剂型结尾）
  const nameMatch = text.match(
    /(?:吃|服用|开|加|用)\s*(?:了|点|上)?\s*([\u4e00-\u9fa5A-Za-z0-9]{1,15}?(?:片|胶囊|颗粒|丸|注射液|口服液|软膏|滴眼液|喷雾|贴剂|散))/
  )
  if (!nameMatch) return null
  const medicationName = nameMatch[1].replace(/^\d+/, '').trim()
  if (medicationName.length < 2) return null

  const doseMatch = text.match(/(\d+(?:\.\d+)?)\s*(mg|毫克|g|克|片|粒|ml|毫升|袋|支|单位)/i)
  const dose = doseMatch ? Number(doseMatch[1]) : undefined
  const doseUnit = doseMatch ? doseMatch[2] : undefined

  let frequency: string | undefined
  for (const row of FREQ_WORDS) {
    if (row.words.some((w) => text.includes(w))) {
      frequency = row.key
      break
    }
  }

  const doseStr = dose ? `${dose}${doseUnit || ''}` : ''
  return {
    kind: 'medication',
    medication_name: medicationName,
    dose,
    dose_unit: doseUnit,
    frequency,
    label: `${medicationName} ${doseStr}`.trim(),
    raw: text,
  }
}

/**
 * 主入口：按规格表格顺序匹配，只取第一个意图。
 * 询问数字、报告已服药都不弹确认卡（IO_SPEC §2.2）。
 * @returns HealthDraft 或 null（没听清/无法解析/不需要写库）
 */
export function parseHealthParams(input: string): HealthDraft | null {
  const text = (input || '').trim()
  if (!text) return null

  const questionWords = ['算高吗', '算低吗', '高吗', '低吗', '正常吗', '怎么样', '咋样', '严重吗', '要紧吗', '是否', '是不是', '吗', '？', '?']
  const writeWords = ['记录', '记一下', '帮我记', '录入', '保存', '添加', '写进']
  const intakeWords = ['吃了', '刚吃', '服用了', '吃过', '喝了一片', '已服']

  if (questionWords.some((w) => text.includes(w)) && !writeWords.some((w) => text.includes(w))) {
    return null
  }
  if (intakeWords.some((w) => text.includes(w))) {
    return null
  }

  return (
    parseBloodGlucose(text) ||
    parseBloodPressure(text) ||
    parseWeight(text) ||
    parseHeartRate(text) ||
    parseSpo2(text) ||
    parseBloodLipid(text) ||
    parseMedication(text) ||
    null
  )
}
