/**
 * 语音播报偏好（本地持久化）。
 * 规格 §6.5.4 语音分组：播报开关 / 音量 / 语速。
 * 注：后端 /voice/tts 不接受语速/音量参数，这里作用于浏览器播放层
 * （HTMLAudioElement.volume / playbackRate）。
 */
export interface VoiceSettings {
  enabled: boolean
  volume: number // 0-100
  rate: number // 0.5-2.0
}

const KEY = 'voice_settings'

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  enabled: true,
  volume: 80,
  rate: 1,
}

export function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULT_VOICE_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<VoiceSettings>
    return {
      ...DEFAULT_VOICE_SETTINGS,
      ...parsed,
      volume: clamp(Number(parsed.volume ?? DEFAULT_VOICE_SETTINGS.volume), 0, 100),
      rate: clamp(Number(parsed.rate ?? DEFAULT_VOICE_SETTINGS.rate), 0.5, 2),
    }
  } catch {
    return { ...DEFAULT_VOICE_SETTINGS }
  }
}

export function saveVoiceSettings(settings: VoiceSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    /* ignore */
  }
}

function clamp(n: number, min: number, max: number): number {
  if (Number.isNaN(n)) return min
  return Math.min(max, Math.max(min, n))
}
