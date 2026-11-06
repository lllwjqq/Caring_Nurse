/**
 * 服药打卡本机存储（规格 §1.3 前端降级）。
 * 后端无打卡字段/日志表，仅保存在本机 localStorage，UI 明确标注「仅本机记录」。
 */
export type CheckStatus = 'taken' | 'skipped'

export interface CheckEntry {
  status: CheckStatus
  /** 打卡时间 HH:MM（仅 taken 时记录） */
  time?: string
}

export type CheckMap = Record<string, CheckEntry>

const PREFIX = 'med_checks'

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

export function todayDate(): string {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function nowHHMM(): string {
  const d = new Date()
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function storageKey(date: string): string {
  return `${PREFIX}:${date}`
}

export function loadChecks(date = todayDate()): CheckMap {
  try {
    const raw = localStorage.getItem(storageKey(date))
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, CheckEntry>
    const out: CheckMap = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (value && (value.status === 'taken' || value.status === 'skipped')) {
        out[key] = { status: value.status, time: value.time }
      }
    }
    return out
  } catch {
    return {}
  }
}

export function saveChecks(checks: CheckMap, date = todayDate()): void {
  try {
    localStorage.setItem(storageKey(date), JSON.stringify(checks))
  } catch {
    /* localStorage 不可用时静默降级 */
  }
}
