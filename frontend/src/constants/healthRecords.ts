export const RECORD_TYPES = [
  { value: 'blood_glucose', label: '血糖', unit: 'mmol/L' },
  { value: 'blood_pressure', label: '血压', unit: 'mmHg' },
  { value: 'weight', label: '体重', unit: 'kg' },
  { value: 'blood_lipid', label: '血脂', unit: 'mmol/L' },
  { value: 'spo2', label: '血氧', unit: '%' },
] as const

export const RECORD_TYPE_LABELS: Record<string, string> = {
  blood_glucose: '血糖',
  blood_pressure: '血压',
  weight: '体重',
  blood_lipid: '血脂',
  spo2: '血氧',
  heart_rate: '心率',
}

export const GLUCOSE_CONTEXTS = [
  { value: 'fasting', label: '空腹', referenceRange: '4.4-7.0 mmol/L' },
  { value: 'postprandial', label: '餐后2h', referenceRange: '<10.0 mmol/L' },
  { value: 'random', label: '随机', referenceRange: '<11.1 mmol/L' },
  { value: 'bedtime', label: '睡前', referenceRange: '4.4-8.0 mmol/L' },
] as const

export type GlucoseContext = (typeof GLUCOSE_CONTEXTS)[number]['value']

export const GLUCOSE_CONTEXT_LABELS: Record<string, string> = Object.fromEntries(
  GLUCOSE_CONTEXTS.map((c) => [c.value, c.label]),
)

const REFERENCE_RANGES: Record<string, Record<string, string>> = {
  blood_glucose: {
    value: '4.4-7.0 mmol/L',
    fasting: '4.4-7.0 mmol/L',
    postprandial: '<10.0 mmol/L',
    random: '<11.1 mmol/L',
    bedtime: '4.4-8.0 mmol/L',
  },
  blood_pressure: { value: '收缩压 90-140 / 舒张压 60-90 mmHg' },
  weight: { value: '因个人目标而异' },
  blood_lipid: { value: 'LDL-C <3.4 mmol/L' },
  spo2: { value: '≥94%' },
}

export function getReferenceRange(recordType: string, context?: string): string {
  const ranges = REFERENCE_RANGES[recordType]
  if (!ranges) return ''
  if (context && ranges[context]) return ranges[context]
  return ranges.value || ''
}

export interface HealthRecordItem {
  id: number
  patient_id: number
  record_type: string
  value: number
  unit: string
  extra_data?: { type?: string; systolic?: number; diastolic?: number; note?: string } | null
  recorded_at: string
  is_abnormal: boolean
}

export interface RecordFeedback {
  is_abnormal: boolean
  alert_level: string | null
  reference_range: string | null
  message: string
  alert_id: number | null
}

export interface HealthRecordCreateResult {
  record: HealthRecordItem
  feedback: RecordFeedback
}

export function formatRecordValue(record: HealthRecordItem): string {
  if (record.record_type === 'blood_pressure' && record.extra_data) {
    const sys = record.extra_data.systolic ?? record.value
    const dia = record.extra_data.diastolic
    return dia != null ? `${sys}/${dia} ${record.unit}` : `${sys} ${record.unit}`
  }
  return `${record.value} ${record.unit}`
}

export function formatRecordLabel(record: HealthRecordItem): string {
  const base = RECORD_TYPE_LABELS[record.record_type] || record.record_type
  const ctx = record.extra_data?.type
  if (record.record_type === 'blood_glucose' && ctx) {
    const ctxLabel = GLUCOSE_CONTEXT_LABELS[ctx]
    return ctxLabel ? `${ctxLabel}${base}` : base
  }
  return base
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function toLocalDatetimeValue(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export const FEEDBACK_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  green: { bg: 'bg-green-50', text: 'text-green-800', border: 'border-green-200' },
  yellow: { bg: 'bg-yellow-50', text: 'text-yellow-800', border: 'border-yellow-200' },
  orange: { bg: 'bg-orange-50', text: 'text-orange-800', border: 'border-orange-200' },
  red: { bg: 'bg-red-50', text: 'text-red-800', border: 'border-red-200' },
}
