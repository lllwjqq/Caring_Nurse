/** 前端共享数据类型（对齐后端返回契约，见规格 §12）。 */

export interface MeUser {
  id: number
  email: string
  full_name: string
  role: string
  agreed_disclaimer: boolean
}

export interface PatientProfile {
  id: number
  user_id: number
  gender: string | null
  birth_date: string | null
  height_cm: number | null
  weight_kg: number | null
  diseases: string[]
  allergies: string | null
  medications: string | null
  emergency_contact: string | null
  health_profile: Record<string, unknown> | null
  created_at: string
}

export interface AlertItem {
  id: number
  patient_id: number
  level: 'green' | 'yellow' | 'orange' | 'red' | string
  level_label?: string
  title: string
  message: string
  source: string
  source_label?: string
  suggestion: string | null
  is_read: boolean
  is_resolved: boolean
  created_at: string
}

export interface ReminderItem {
  id: number
  patient_id: number
  medication_name: string
  brand_name?: string | null
  spec?: string | null
  dose?: number | null
  dose_unit?: string | null
  frequency: string
  times_of_day: string[] | null
  route?: string | null
  timing_note?: string | null
  start_date?: string | null
  end_date?: string | null
  notes?: string | null
  source_document_id?: number | null
  active: boolean
  created_at: string
}

export interface CarePlanItem {
  id: number
  patient_id: number
  title: string
  diet_plan?: { items?: string[] } | null
  exercise_plan?: { items?: string[] } | null
  monitoring_plan?: { items?: string[] } | null
  medication_notes?: string | null
  status: string
  created_by_agent: string
  created_at: string
}

export interface AgentAction {
  type: string
  summary?: string
  target?: string
  level?: string
  message?: string
  record_id?: number
  reminder_id?: number
}

export interface AgentEvidence {
  source?: string
  title?: string
  snippet?: string
  relation?: string
  score?: number
}

export interface AgentPresentation {
  summary?: string
  key_points?: string[]
  action_items?: string[]
  boundary?: string
  tts_text?: string
}

export interface ParsedMetric {
  record_type: string
  name: string
  value: number | null
  unit: string
  context?: string | null
  systolic?: number | null
  diastolic?: number | null
  reference?: string | null
  abnormal_flag?: string | null
  confidence?: number
}

export interface ParsedMedication {
  name: string
  generic_name?: string | null
  brand_name?: string | null
  spec?: string | null
  dose?: number | null
  dose_unit?: string | null
  frequency?: string
  route?: string | null
  timing_note?: string | null
  duration_days?: number | null
  notes?: string | null
  confidence?: number
}

export interface ParsedDocumentData {
  doc_type: string
  confidence?: number
  exam_date?: string | null
  metrics?: ParsedMetric[]
  medications?: ParsedMedication[]
  status_text?: string | null
  questions_to_ask?: string[]
  modules?: Record<string, { label: string; items: string[] }>
  drug_matches?: Array<{ name: string; brand_names?: string[]; spec?: string | null }>
  manual_input_required?: boolean
}

export interface MedicalDocumentItem {
  id: number
  patient_id: number
  filename: string
  doc_type: string
  confidence: number | null
  ocr_text: string | null
  parsed_data: ParsedDocumentData | null
  status: string
  created_at: string
}

export interface DiagnosisItem {
  id: number
  patient_id: number
  name: string
  diagnosed_at: string | null
  doc_type: string
  source_document_id: number | null
  status: 'current' | 'past'
  notes: string | null
  created_at: string
}

export interface AppointmentItem {
  id: number
  patient_id: number
  title: string
  department: string | null
  due_at: string
  source_document_id: number | null
  status: 'pending' | 'done' | 'cancelled'
  created_at: string
}

export const DISEASE_LABELS: Record<string, string> = {
  diabetes_type2: '2型糖尿病',
  hypertension: '高血压',
  hyperlipidemia: '高血脂',
  copd: '慢阻肺',
}

export const LEVEL_LABELS: Record<string, string> = {
  green: '稳定',
  yellow: '需要关注',
  orange: '警告',
  red: '危险',
}

export const LEVEL_ORDER: Record<string, number> = {
  red: 4,
  orange: 3,
  yellow: 2,
  green: 1,
}

export const DOC_TYPE_LABELS: Record<string, string> = {
  lab_report: '体检/化验单',
  prescription: '处方/医嘱',
  discharge_summary: '出院小结',
  outpatient_record: '门诊病历',
  drug_insert: '药品说明书',
  other: '其他文档',
}

export const DOC_STATUS_LABELS: Record<string, string> = {
  confirmed: '已确认',
  discarded: '已放弃',
  awaiting_confirmation: '待确认',
  uploaded: '待处理',
}
