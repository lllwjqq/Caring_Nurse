import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { voiceApi } from '../api/client'
import { loadVoiceSettings, saveVoiceSettings, type VoiceSettings } from '../lib/voiceSettings'
import { parseHealthParams, type HealthDraft } from '../lib/parseHealthParams'

interface VoiceContextValue extends VoiceSettings {
  speaking: boolean
  /** 播报（返回 false 表示被禁用或浏览器拦截） */
  speak: (text: string, force?: boolean) => Promise<boolean>
  stop: () => void
  setEnabled: (enabled: boolean) => void
  setVolume: (volume: number) => void
  setRate: (rate: number) => void
  /** 语音导入草稿（全局确认卡） */
  draft: HealthDraft | null
  setDraft: (draft: HealthDraft | null) => void
  clearDraft: () => void
  /** 文本 → 草稿；解析失败返回 false */
  processTranscript: (text: string) => boolean
  /** 识别成功、但不是健康数据/用药的文本，排队交给问诊页消费 */
  pendingTranscript: string | null
  /** 把无法解析的语音文本排队（悬浮球用） */
  queueTranscript: (text: string) => void
  /** 取出并清空排队的语音文本（问诊页用） */
  takePendingTranscript: () => string | null
}

const VoiceContext = createContext<VoiceContextValue | null>(null)

export function VoiceProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<VoiceSettings>(() => loadVoiceSettings())
  const [speaking, setSpeaking] = useState(false)
  const [draft, setDraft] = useState<HealthDraft | null>(null)
  // 无法解析为健康数据的语音文本：悬浮球排队，问诊页取走并自动发送
  const [pendingTranscript, setPendingTranscript] = useState<string | null>(null)
  const pendingRef = useRef<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlRef = useRef<string | null>(null)
  const unlockedRef = useRef(false)
  const cacheRef = useRef<Map<string, Blob>>(new Map())

  // 持久化语音偏好
  useEffect(() => {
    saveVoiceSettings(settings)
  }, [settings])

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.onended = null
      audioRef.current.onerror = null
      audioRef.current = null
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
    setSpeaking(false)
  }, [])

  const speak = useCallback(
    async (text: string, force = false): Promise<boolean> => {
      const content = (text || '').trim()
      if (!content) return false
      if (!force && !settings.enabled) return false
      stop()
      try {
        let blob = cacheRef.current.get(content)
        if (!blob) {
          const { data } = await voiceApi.tts(content)
          blob = data as Blob
          // 简单缓存，避免重复点击重复合成
          if (cacheRef.current.size > 30) cacheRef.current.clear()
          cacheRef.current.set(content, blob)
        }
        const url = URL.createObjectURL(blob)
        urlRef.current = url
        const audio = new Audio(url)
        audio.volume = Math.min(1, Math.max(0, settings.volume / 100))
        audio.playbackRate = Math.min(2, Math.max(0.5, settings.rate))
        audioRef.current = audio
        audio.onended = () => {
          setSpeaking(false)
          if (urlRef.current === url) {
            URL.revokeObjectURL(url)
            urlRef.current = null
          }
        }
        audio.onerror = () => {
          setSpeaking(false)
          if (urlRef.current === url) {
            URL.revokeObjectURL(url)
            urlRef.current = null
          }
        }
        setSpeaking(true)
        await audio.play()
        return true
      } catch {
        // 浏览器拦截 / 语音未配置：静默降级（由调用方决定是否脉冲提示）
        setSpeaking(false)
        return false
      }
    },
    [settings.enabled, settings.volume, settings.rate, stop],
  )

  // 首次用户手势解锁浏览器音频播放（规格 §2 音频）
  useEffect(() => {
    const unlock = () => {
      if (unlockedRef.current) return
      unlockedRef.current = true
      try {
        const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        if (Ctx) {
          const ctx = new Ctx()
          void ctx.resume()
        }
      } catch {
        /* ignore */
      }
    }
    window.addEventListener('pointerdown', unlock, { once: true })
    return () => window.removeEventListener('pointerdown', unlock)
  }, [])

  useEffect(() => () => stop(), [stop])

  const processTranscript = useCallback(
    (text: string): boolean => {
      const parsed = parseHealthParams(text)
      if (!parsed) return false
      setDraft(parsed)
      return true
    },
    [],
  )

  const queueTranscript = useCallback((text: string) => {
    pendingRef.current = text
    setPendingTranscript(text)
  }, [])

  const takePendingTranscript = useCallback(() => {
    const text = pendingRef.current
    pendingRef.current = null
    setPendingTranscript(null)
    return text
  }, [])

  const value = useMemo<VoiceContextValue>(
    () => ({
      ...settings,
      speaking,
      speak,
      stop,
      setEnabled: (enabled: boolean) => setSettings((s) => ({ ...s, enabled })),
      setVolume: (volume: number) => setSettings((s) => ({ ...s, volume })),
      setRate: (rate: number) => setSettings((s) => ({ ...s, rate })),
      draft,
      setDraft,
      clearDraft: () => setDraft(null),
      processTranscript,
      pendingTranscript,
      queueTranscript,
      takePendingTranscript,
    }),
    [
      settings,
      speaking,
      speak,
      stop,
      draft,
      processTranscript,
      pendingTranscript,
      queueTranscript,
      takePendingTranscript,
    ],
  )

  return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>
}

export function useVoice(): VoiceContextValue {
  const ctx = useContext(VoiceContext)
  if (!ctx) throw new Error('useVoice must be used within VoiceProvider')
  return ctx
}
