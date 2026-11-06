import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAlert } from '../context/AlertContext'
import { useVoice } from '../context/VoiceContext'
import { useToast } from './Toast'
import { MicIcon } from './icons'
import { useVoiceRecorder } from '../lib/useVoiceRecorder'

const SIZE = 64
const MARGIN = 16
const STORAGE_KEY = 'orb_position'
const BREATH_KEY = 'orb_breathed'
/** 按住多久才进入录音：这段时间内移动视为拖动，不触发录音 */
const HOLD_DELAY = 300
/** 判定为拖动的最小位移 */
const DRAG_THRESHOLD = 16
/** 短于该时长不送识别，避免空音频请求 */
const MIN_RECORD_MS = 500

interface Pos {
  x: number
  y: number
}

interface Gesture {
  mode: 'pending' | 'drag' | 'record'
  startX: number
  startY: number
  originX: number
  originY: number
  startedAt: number
  recordStartedAt: number
}

function readStored(): Pos | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<Pos>
    if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
      return { x: parsed.x, y: parsed.y }
    }
  } catch {
    /* ignore */
  }
  return null
}

function shellRect(): DOMRect | null {
  return document.getElementById('app-shell')?.getBoundingClientRect() ?? null
}

/** 夹紧到页头与 TabBar 之间；问诊页再抬到输入区上沿（规格 §4.4）。 */
function clampPos(pos: Pos): Pos {
  const shell = shellRect()
  if (!shell) return pos
  const header = document.getElementById('page-header')?.getBoundingClientRect()
  const tabbar = document.getElementById('tab-bar')?.getBoundingClientRect()
  const anchor = document.getElementById('orb-upper-bound')?.getBoundingClientRect()

  const minX = shell.left + MARGIN
  const maxX = shell.right - MARGIN - SIZE
  const minY = (header ? header.bottom : shell.top) + 8
  let maxY = (tabbar ? tabbar.top : shell.bottom) - 12 - SIZE
  if (anchor && anchor.height > 0) maxY = Math.min(maxY, anchor.top - 12 - SIZE)

  return {
    x: Math.min(Math.max(pos.x, minX), Math.max(minX, maxX)),
    y: Math.min(Math.max(pos.y, minY), Math.max(minY, maxY)),
  }
}

function defaultPos(): Pos {
  const shell = shellRect()
  if (!shell) return { x: 16, y: 320 }
  return {
    x: shell.right - MARGIN - SIZE,
    y: shell.top + shell.height * 0.58 - SIZE / 2,
  }
}

function levelTemplate(level: string, title: string): string {
  if (level === 'red') return `小护士提醒您：${title}。请立即联系医生或拨打 120。`
  if (level === 'orange') return `小护士提醒您：${title}。建议尽快联系医生。`
  if (level === 'yellow') return `小护士提醒您：${title}。先休息一下，再测一次。`
  return ''
}

/**
 * 全局语音悬浮球（规格 §4.4）：
 * - 按住后先等待 300ms：这期间移动 = 拖动换位，不录音；
 * - 按住不动超过 300ms = 开始录音，松手识别；
 * - 快速轻点不录音，只给手势提示；
 * - 预警到达时脉冲 + 气泡 + 语音播报。
 *
 * 注意：录音启动延迟到 hold 定时器里，是为了让「拖动」和「说话」用同一个按钮
 * 也能区分开；代价是 getUserMedia 不在 pointerdown 的同步调用栈内，个别浏览器
 * 首次授权可能更慢。若真机上录音启动失败，优先检查麦克风权限。
 */
export default function VoiceOrb() {
  const { latestAlert } = useAlert()
  const { enabled, speak, processTranscript, queueTranscript, speaking, stop: stopSpeaking } = useVoice()
  const { showToast } = useToast()
  const { recording, recognizing, starting, start, stop, cancel } = useVoiceRecorder()
  const { pathname } = useLocation()
  const navigate = useNavigate()

  const [pos, setPos] = useState<Pos>({ x: 16, y: 320 })
  const [pulse, setPulse] = useState(false)
  const [bubble, setBubble] = useState<string | null>(null)
  const [breathing, setBreathing] = useState(false)
  const [holding, setHolding] = useState(false)
  const [dragging, setDragging] = useState(false)

  const posRef = useRef(pos)
  posRef.current = pos

  const gestureRef = useRef<Gesture | null>(null)
  const holdTimerRef = useRef<number | null>(null)
  const failedRef = useRef(false)

  const clearHoldTimer = useCallback(() => {
    if (holdTimerRef.current !== null) {
      window.clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
    }
  }, [])

  // 初始化位置 + 复位事件 + 窗口尺寸变化
  useLayoutEffect(() => {
    setPos(clampPos(readStored() ?? defaultPos()))
    const onResize = () => setPos((p) => clampPos(p))
    const onReset = () => {
      try {
        localStorage.removeItem(STORAGE_KEY)
      } catch {
        /* ignore */
      }
      setPos(clampPos(defaultPos()))
    }
    window.addEventListener('resize', onResize)
    window.addEventListener('orb-reset', onReset)
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('orb-reset', onReset)
    }
  }, [])

  // 路由切换后重新夹紧（问诊页输入区上沿可能变化）
  useEffect(() => {
    setPos((p) => clampPos(p))
  }, [pathname])

  // 首次进入呼吸一次
  useEffect(() => {
    try {
      if (!localStorage.getItem(BREATH_KEY)) {
        setBreathing(true)
        localStorage.setItem(BREATH_KEY, '1')
        const t = window.setTimeout(() => setBreathing(false), 5000)
        return () => window.clearTimeout(t)
      }
    } catch {
      /* ignore */
    }
  }, [])

  // 预警到达：脉冲 + 气泡 + 语音
  const lastAlertRef = useRef<number | null>(null)
  useEffect(() => {
    if (!latestAlert) return
    if (lastAlertRef.current === latestAlert.id) return
    lastAlertRef.current = latestAlert.id
    if (latestAlert.level === 'green') return

    setPulse(true)
    setBubble('有 1 条提醒')
    const stopPulse = window.setTimeout(() => setPulse(false), 1500)
    const hideBubble = window.setTimeout(() => setBubble(null), 4500)

    if (enabled) {
      void speak(levelTemplate(latestAlert.level, latestAlert.title))
    }
    return () => {
      window.clearTimeout(stopPulse)
      window.clearTimeout(hideBubble)
    }
  }, [latestAlert, enabled, speak])

  // 卸载时清理计时器并放弃未完成的录音
  useEffect(
    () => () => {
      clearHoldTimer()
      void cancel()
    },
    [cancel, clearHoldTimer],
  )

  const beginRecording = useCallback(() => {
    const gesture = gestureRef.current
    if (!gesture || gesture.mode !== 'pending') return
    gesture.mode = 'record'
    gesture.recordStartedAt = Date.now()
    setHolding(true)
    if (speaking) stopSpeaking()

    void start().catch(() => {
      failedRef.current = true
      gestureRef.current = null
      setHolding(false)
      showToast('无法访问麦克风，请允许麦克风权限或改用打字')
    })
  }, [speaking, stopSpeaking, start, showToast])

  const finishDrag = useCallback(() => {
    setDragging(false)
    const shell = shellRect()
    let x = posRef.current.x
    if (shell) {
      const center = posRef.current.x + SIZE / 2
      x = center < shell.left + shell.width / 2 ? shell.left + MARGIN : shell.right - MARGIN - SIZE
    }
    const next = clampPos({ x, y: posRef.current.y })
    setPos(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* ignore */
    }
  }, [])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      if (e.button !== 0 || gestureRef.current || recognizing) return
      e.preventDefault()
      try {
        e.currentTarget.setPointerCapture(e.pointerId)
      } catch {
        /* 某些浏览器/合成事件可能不支持捕获，忽略即可 */
      }

      failedRef.current = false
      gestureRef.current = {
        mode: 'pending',
        startX: e.clientX,
        startY: e.clientY,
        originX: posRef.current.x,
        originY: posRef.current.y,
        startedAt: Date.now(),
        recordStartedAt: 0,
      }

      clearHoldTimer()
      holdTimerRef.current = window.setTimeout(beginRecording, HOLD_DELAY)
    },
    [beginRecording, clearHoldTimer, recognizing],
  )

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      const gesture = gestureRef.current
      if (!gesture) return

      if (gesture.mode === 'pending') {
        if (Math.hypot(e.clientX - gesture.startX, e.clientY - gesture.startY) > DRAG_THRESHOLD) {
          clearHoldTimer()
          gesture.mode = 'drag'
          setDragging(true)
          setHolding(false)
        }
        return
      }

      if (gesture.mode === 'drag') {
        setPos(
          clampPos({
            x: gesture.originX + (e.clientX - gesture.startX),
            y: gesture.originY + (e.clientY - gesture.startY),
          }),
        )
      }
      // mode === 'record'：录音期间忽略移动
    },
    [clearHoldTimer],
  )

  const handlePointerUp = useCallback(async () => {
    const gesture = gestureRef.current
    if (!gesture) return
    clearHoldTimer()
    gestureRef.current = null

    if (gesture.mode === 'drag') {
      finishDrag()
      return
    }

    if (gesture.mode === 'pending') {
      // 还没到录音时长就松手：给一次手势提示，不送识别
      setHolding(false)
      showToast('按住说话；按住后移动可拖动')
      return
    }

    if (failedRef.current) {
      failedRef.current = false
      setHolding(false)
      return
    }

    const heldFor = Date.now() - gesture.recordStartedAt
    if (heldFor < MIN_RECORD_MS) {
      setHolding(false)
      await cancel()
      showToast('按住说话，说完再松手')
      return
    }

    try {
      const text = await stop()
      if (!text) {
        showToast('没太听清，能再说一次吗？')
        return
      }
      if (!processTranscript(text)) {
        // 不是健康数据/用药：当作问诊问题交给问诊页，自动发送给智能体
        queueTranscript(text)
        if (pathname !== '/') navigate('/')
      }
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      showToast(
        status === 503
          ? '语音服务未配置'
          : status === 400
            ? '说话时间太短，请按住多说一会儿'
            : '语音识别失败，请改用文字输入',
      )
    } finally {
      setHolding(false)
    }
  }, [cancel, finishDrag, navigate, pathname, processTranscript, queueTranscript, showToast, stop])

  const handlePointerCancel = useCallback(() => {
    const gesture = gestureRef.current
    gestureRef.current = null
    clearHoldTimer()
    setHolding(false)
    if (!gesture) return
    if (gesture.mode === 'drag') {
      finishDrag()
      return
    }
    if (gesture.mode === 'record') {
      void cancel()
    }
  }, [cancel, clearHoldTimer, finishDrag])

  const recordingNow = holding || recording
  const hint = recognizing
    ? '正在识别…'
    : recordingNow
      ? '正在聆听… 松开结束'
      : starting
        ? '准备中…'
        : bubble
  const hintClass =
    recordingNow || recognizing ? 'bg-level-red' : starting ? 'bg-level-orange' : 'bg-ink'
  const bubbleLeft = pos.x + SIZE / 2

  return (
    <>
      {hint && (
        <div
          role="status"
          aria-live="polite"
          className={`pointer-events-none fixed z-30 -translate-x-1/2 whitespace-nowrap rounded-full px-4 py-2 text-white ${hintClass}`}
          style={{ left: bubbleLeft, top: Math.max(8, pos.y - 44) }}
        >
          <span className="t-cap leading-none">{hint}</span>
        </div>
      )}

      <button
        type="button"
        aria-label="按住说话；按住后移动可拖动"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onContextMenu={(e) => e.preventDefault()}
        className={`fixed z-30 flex items-center justify-center rounded-full text-white shadow-card-lg ${
          recordingNow ? 'bg-level-red' : starting ? 'bg-level-orange' : ''
        } ${pulse ? 'animate-orb-pulse' : ''} ${breathing && !recordingNow && !dragging ? 'animate-orb-breathe' : ''}`}
        style={{
          left: pos.x,
          top: pos.y,
          width: SIZE,
          height: SIZE,
          touchAction: 'none',
          userSelect: 'none',
          cursor: dragging ? 'grabbing' : 'pointer',
          backgroundImage:
            recordingNow || starting
              ? undefined
              : 'linear-gradient(135deg, rgb(var(--c-primary)), rgb(var(--c-primary-deep)))',
        }}
      >
        <MicIcon size={28} />
      </button>
    </>
  )
}
