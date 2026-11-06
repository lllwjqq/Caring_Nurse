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
import { useNavigate } from 'react-router-dom'
import { authApi, featureApi, patientApi } from '../api/client'
import type { AlertItem, MeUser, PatientProfile } from '../lib/types'

interface AlertContextValue {
  patient: PatientProfile | null
  user: MeUser | null
  alerts: AlertItem[]
  unreadCount: number
  latestAlert: AlertItem | null
  loading: boolean
  refresh: () => Promise<void>
  refreshPatient: () => Promise<void>
  markRead: (id: number) => Promise<void>
  markAllRead: () => Promise<void>
  resolveAlert: (id: number) => Promise<void>
  consumeLatest: () => void
}

const AlertContext = createContext<AlertContextValue | null>(null)

/** WS 推送体（Redis 发布）字段不全，补默认值。 */
function normalizeWsAlert(raw: unknown): AlertItem | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  if (obj.id == null) return null // 服药提醒（id:null）不进入预警流
  return {
    id: Number(obj.id),
    patient_id: Number(obj.patient_id ?? 0),
    level: String(obj.level ?? 'yellow'),
    level_label: obj.level_label == null ? undefined : String(obj.level_label),
    title: String(obj.title ?? '健康提醒'),
    message: String(obj.message ?? ''),
    source: String(obj.source ?? 'system'),
    source_label: obj.source_label == null ? undefined : String(obj.source_label),
    suggestion: obj.suggestion == null ? null : String(obj.suggestion),
    is_read: false,
    is_resolved: false,
    created_at: String(obj.created_at ?? new Date().toISOString()),
  }
}

export function AlertProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [patient, setPatient] = useState<PatientProfile | null>(null)
  const [user, setUser] = useState<MeUser | null>(null)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [latestAlert, setLatestAlert] = useState<AlertItem | null>(null)
  const [loading, setLoading] = useState(true)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef(0)
  const timersRef = useRef<number[]>([])
  const pollingRef = useRef<number | null>(null)

  const clearTimer = useCallback(() => {
    timersRef.current.forEach((t) => window.clearTimeout(t))
    timersRef.current = []
    if (pollingRef.current) {
      window.clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const { data } = await featureApi.listAlerts(true)
      setAlerts(data as AlertItem[])
    } catch {
      /* 失败保留现状，交给三态展示 */
    }
  }, [])

  const refreshPatient = useCallback(async () => {
    try {
      const { data } = await patientApi.getProfile()
      setPatient(data as PatientProfile)
    } catch {
      /* ignore */
    }
  }, [])

  // 患者 / 用户资料
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [meRes, patientRes] = await Promise.all([authApi.me(), patientApi.getProfile()])
        if (cancelled) return
        setUser(meRes.data as MeUser)
        setPatient(patientRes.data as PatientProfile)
      } catch (err) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 404) navigate('/setup', { replace: true })
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [navigate])

  // 初始预警
  useEffect(() => {
    if (patient) void refresh()
  }, [patient, refresh])

  // 实时预警 WebSocket（含重连与轮询降级）
  useEffect(() => {
    const patientId = patient?.id
    if (!patientId) return
    let disposed = false

    const startPolling = () => {
      if (pollingRef.current) return
      pollingRef.current = window.setInterval(() => void refresh(), 60_000)
    }

    const connect = () => {
      if (disposed) return
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      // WS 鉴权：access token 走 query（规格附录 A.4）
      const token = localStorage.getItem('access_token')
      const query = token ? `?token=${encodeURIComponent(token)}` : ''
      const ws = new WebSocket(
        `${proto}://${window.location.host}/api/ws/alerts/${patientId}${query}`,
      )
      wsRef.current = ws

      ws.onopen = () => {
        reconnectRef.current = 0
      }
      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data as string) as unknown
          if ((parsed as { type?: string })?.type === 'pong') return
          const alert = normalizeWsAlert(parsed)
          if (!alert) return
          setAlerts((prev) => (prev.some((a) => a.id === alert.id) ? prev : [alert, ...prev]))
          setLatestAlert(alert)
        } catch {
          /* 非 JSON 帧忽略 */
        }
      }
      ws.onclose = (event) => {
        if (disposed) return
        // 鉴权失败（4401）不重连，交给 HTTP 拦截器处理登录态
        if (event.code === 4401) return
        reconnectRef.current += 1
        if (reconnectRef.current <= 5) {
          const delay = Math.min(30_000, 1000 * 2 ** (reconnectRef.current - 1))
          timersRef.current.push(window.setTimeout(connect, delay))
        } else {
          startPolling()
        }
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      disposed = true
      wsRef.current?.close()
      wsRef.current = null
      clearTimer()
    }
  }, [patient?.id, refresh, clearTimer])

  const unreadCount = useMemo(() => alerts.filter((a) => !a.is_read).length, [alerts])

  const markRead = useCallback(async (id: number) => {
    try {
      await featureApi.markAlertRead(id)
    } catch {
      /* ignore */
    }
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true } : a)))
  }, [])

  const markAllRead = useCallback(async () => {
    const unread = alerts.filter((a) => !a.is_read)
    if (!unread.length) return
    await Promise.all(
      unread.map((a) =>
        featureApi.markAlertRead(a.id).catch(() => {
          /* ignore */
        }),
      ),
    )
    setAlerts((prev) => prev.map((a) => ({ ...a, is_read: true })))
  }, [alerts])

  const resolveAlert = useCallback(async (id: number) => {
    try {
      await featureApi.resolveAlert(id)
    } catch {
      /* ignore */
    }
    setAlerts((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const consumeLatest = useCallback(() => setLatestAlert(null), [])

  const value = useMemo<AlertContextValue>(
    () => ({
      patient,
      user,
      alerts,
      unreadCount,
      latestAlert,
      loading,
      refresh,
      refreshPatient,
      markRead,
      markAllRead,
      resolveAlert,
      consumeLatest,
    }),
    [patient, user, alerts, unreadCount, latestAlert, loading, refresh, refreshPatient, markRead, markAllRead, resolveAlert, consumeLatest],
  )

  return <AlertContext.Provider value={value}>{children}</AlertContext.Provider>
}

export function useAlert(): AlertContextValue {
  const ctx = useContext(AlertContext)
  if (!ctx) throw new Error('useAlert must be used within AlertProvider')
  return ctx
}
