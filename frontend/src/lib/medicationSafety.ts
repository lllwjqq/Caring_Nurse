/**
 * 用药安全规则引擎（规格 §6.4.3）。
 * 后端无相互作用/过敏检查，前端做确定性规则提示，不构成医疗建议。
 */
import type { ReminderItem } from './types'

export type SafetyLevel = 'red' | 'orange' | 'yellow'

export interface SafetyIssue {
  level: SafetyLevel
  title: string
  why: string
  advice: string
  related: string[]
}

export interface SafetyInput {
  allergies?: string | null
  longTermMeds?: string | null
  reminders: ReminderItem[]
}

const DOSE_UNITS = ['片', '粒', '袋', '支']

function normalizeName(name: string): string {
  return name
    .replace(/(缓释|控释|肠溶|咀嚼|分散|泡腾|胶囊|颗粒|口服液|软膏|滴眼液|喷雾|贴剂|散|丸|片|注射液)/g, '')
    .replace(/\d+(\.\d+)?\s*(mg|g|ml|毫克|克|毫升)/gi, '')
    .trim()
}

const INTERACTIONS: Array<{ a: string[]; b: string[]; why: string; advice: string }> = [
  {
    a: ['阿司匹林', '氯吡格雷'],
    b: ['华法林'],
    why: '抗血小板与抗凝作用叠加，出血风险升高',
    advice: '请咨询医生是否需要调整剂量或加做凝血监测',
  },
  {
    a: ['二甲双胍'],
    b: ['造影剂', '含碘'],
    why: '可能增加肾功能损伤与乳酸酸中毒风险',
    advice: '做增强 CT 或造影前后，请告知医生正在服用二甲双胍',
  },
  {
    a: ['硝苯地平'],
    b: ['西柚', '柚子'],
    why: '可能抑制药物代谢，导致血压过低',
    advice: '服药期间避免食用西柚或饮用西柚汁',
  },
  {
    a: ['他汀', '阿托伐他汀', '瑞舒伐他汀', '辛伐他汀'],
    b: ['克拉霉素', '红霉素'],
    why: '可能升高他汀血药浓度，增加肌痛与肝损伤风险',
    advice: '请告知医生，必要时换用其他抗生素',
  },
]

/** 返回按严重度排序的用药安全提示。 */
export function checkMedicationSafety(input: SafetyInput): SafetyIssue[] {
  const reminders = input.reminders
  const allergies = (input.allergies ?? '')
    .split(/[、,，;；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  const extraMeds = (input.longTermMeds ?? '')
    .split(/[、,，;；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)

  const issues: SafetyIssue[] = []

  // S1 过敏冲突
  for (const r of reminders) {
    const hit = allergies.find((a) => r.medication_name.includes(a))
    if (hit) {
      issues.push({
        level: 'red',
        title: `过敏风险：${r.medication_name}`,
        why: `药名包含您的过敏原「${hit}」`,
        advice: '请立即停用并联系医生确认替代用药',
        related: [r.medication_name],
      })
    }
  }

  // S2 重复用药
  const groups = new Map<string, ReminderItem[]>()
  for (const r of reminders) {
    const key = normalizeName(r.medication_name)
    if (!key) continue
    const arr = groups.get(key) ?? []
    arr.push(r)
    groups.set(key, arr)
  }
  for (const [key, arr] of groups) {
    if (arr.length >= 2) {
      issues.push({
        level: 'orange',
        title: `重复用药：${key}`,
        why: `有 ${arr.length} 条提醒含相同成分`,
        advice: '请确认是否重复开药，避免叠加用药',
        related: arr.map((r) => r.medication_name),
      })
    }
  }

  // S3 剂量缺失 / S4 剂量异常
  for (const r of reminders) {
    if (r.dose == null) {
      issues.push({
        level: 'yellow',
        title: `剂量缺失：${r.medication_name}`,
        why: '未填写单次剂量',
        advice: '请补充剂量并核对医嘱',
        related: [r.medication_name],
      })
      continue
    }
    const unit = (r.dose_unit ?? '').toLowerCase()
    if (DOSE_UNITS.some((u) => unit === u) && r.dose > 5) {
      issues.push({
        level: 'orange',
        title: `剂量偏高：${r.medication_name}`,
        why: `单次 ${r.dose}${r.dose_unit} 超过常见范围`,
        advice: '请核对处方，必要时咨询药师',
        related: [r.medication_name],
      })
    } else if ((unit === 'mg' || unit === '毫克') && r.dose > 1000) {
      issues.push({
        level: 'orange',
        title: `剂量偏高：${r.medication_name}`,
        why: `单次 ${r.dose}mg 超过常见范围`,
        advice: '请核对处方，必要时咨询药师',
        related: [r.medication_name],
      })
    }
  }

  // S5 常见相互作用
  const names = [...reminders.map((r) => r.medication_name), ...extraMeds]
  for (const rule of INTERACTIONS) {
    const hitA = names.find((n) => rule.a.some((x) => n.includes(x)))
    const hitB = names.find((n) => rule.b.some((x) => n.includes(x)))
    if (hitA && hitB && hitA !== hitB) {
      issues.push({
        level: 'orange',
        title: `可能相互作用：${hitA} + ${hitB}`,
        why: rule.why,
        advice: rule.advice,
        related: [hitA, hitB],
      })
      continue
    }
    // 患者长期用药里提到相互作用食物/药物也提示
    if (hitA) {
      const foodHit = extraMeds.find((n) => rule.b.some((x) => n.includes(x)))
      if (foodHit) {
        issues.push({
          level: 'orange',
          title: `注意相互作用：${hitA} 与 ${foodHit}`,
          why: rule.why,
          advice: rule.advice,
          related: [hitA, foodHit],
        })
      }
    }
  }

  const rank: Record<SafetyLevel, number> = { red: 3, orange: 2, yellow: 1 }
  return issues.sort((a, b) => rank[b.level] - rank[a.level])
}
