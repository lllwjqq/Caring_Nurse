import { useCallback, useRef, useState } from 'react'
import { startAudioRecording } from './audio'
import { voiceApi } from '../api/client'

/**
 * 按住说话 → 松手识别。语音悬浮球与问诊输入区共用。
 *
 * 关键点：
 * 1. start() 必须在 pointerdown 的事件栈里同步调用，不能放进 setTimeout，
 *    否则部分浏览器（尤其 iOS Safari）会丢失用户手势，导致 AudioContext 挂起、
 *    录到空音频。这与问诊页「按住说话」按钮的写法保持一致。
 * 2. getUserMedia 是异步的，用户可能在它 resolve 前就松手。startingRef 记录
 *    启动中的 Promise，stop/cancel 会先等它完成再停机，避免空音频或录音流泄漏。
 */
export function useVoiceRecorder() {
  const [recording, setRecording] = useState(false)
  const [recognizing, setRecognizing] = useState(false)
  const [starting, setStarting] = useState(false)
  const recorderRef = useRef<{ stop: () => Promise<Blob> } | null>(null)
  const startingRef = useRef<Promise<void> | null>(null)

  const start = useCallback(async () => {
    if (recorderRef.current) return
    if (startingRef.current) return startingRef.current

    setStarting(true)
    const pending = (async () => {
      const recorder = await startAudioRecording()
      recorderRef.current = recorder
      setRecording(true)
    })()
    startingRef.current = pending
    try {
      await pending
    } finally {
      startingRef.current = null
      setStarting(false)
    }
  }, [])

  const stop = useCallback(async (): Promise<string | null> => {
    if (startingRef.current) {
      // 启动失败由调用方提示；这里只保证不会因竞态卡住
      try {
        await startingRef.current
      } catch {
        /* ignore */
      }
    }
    const recorder = recorderRef.current
    if (!recorder) return null
    recorderRef.current = null
    setRecording(false)
    setRecognizing(true)
    try {
      const blob = await recorder.stop()
      const { data } = await voiceApi.transcribe(blob)
      const text = (data?.text as string | undefined)?.trim() || ''
      return text || null
    } finally {
      setRecognizing(false)
    }
  }, [])

  /** 放弃本次录音：释放麦克风并丢弃音频，不走识别接口。 */
  const cancel = useCallback(async () => {
    if (startingRef.current) {
      try {
        await startingRef.current
      } catch {
        /* ignore */
      }
    }
    const recorder = recorderRef.current
    recorderRef.current = null
    setRecording(false)
    if (recorder) {
      try {
        await recorder.stop()
      } catch {
        /* ignore */
      }
    }
  }, [])

  return { recording, recognizing, starting, start, stop, cancel }
}
