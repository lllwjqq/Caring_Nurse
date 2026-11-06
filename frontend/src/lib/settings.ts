/**
 * 全局显示/提醒设置（本地持久化）。
 * 对应规格 §3.2 大字模式、§6.5.4 设置项。
 */
export interface AppSettings {
  /** 大字模式：切换 CSS 变量字号阶 */
  bigText: boolean
  /** 高对比模式：切换语义色变量 */
  highContrast: boolean
  /** 服药提醒开关（本地偏好，不承诺后台推送） */
  medicationReminder: boolean
  /** 测量提醒开关（文案注明「打开 App 时提醒」） */
  measurementReminder: boolean
}

const KEY = 'app_settings'

export const DEFAULT_SETTINGS: AppSettings = {
  bigText: false,
  highContrast: false,
  medicationReminder: true,
  measurementReminder: true,
}

export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    return { ...DEFAULT_SETTINGS, ...parsed }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    /* localStorage 不可用时静默降级 */
  }
}

/** 把设置落到 <html> 的 data-* 属性上（CSS 变量据此切换）。 */
export function applySettings(settings: AppSettings): void {
  const root = document.documentElement
  root.dataset.textSize = settings.bigText ? 'large' : 'normal'
  root.dataset.contrast = settings.highContrast ? 'high' : 'normal'
}
