import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { appointmentApi, featureApi, healthApi } from '../api/client'
import AlertListItem from '../components/AlertListItem'
import MetricTile from '../components/MetricTile'
import RiskCard from '../components/RiskCard'
import SectionCard from '../components/SectionCard'
import { useToast } from '../components/Toast'
import TrendChart, { type TrendKind } from '../components/TrendChart'
import { useAlert } from '../context/AlertContext'
import {
  formatDateTime,
  formatRecordLabel,
  RECORD_TYPE_LABELS,
  type HealthRecordItem,
} from '../constants/healthRecords'
import { LEVEL_ORDER, type AlertItem, type AppointmentItem } from '../lib/types'

interface Dashboard {
  today_records: HealthRecordItem[]
  recent_alerts: AlertItem[]
  risk_level: string
}

const RISK_COPY: Record<string, string> = {
  green: '今天指标不错，继续保持',
  yellow: '有些指标偏高，注意休息和监测',
  orange: '有指标异常，建议尽快联系医生',
  red: '有严重异常，请立即就医或拨打 120',
}

const TILE_ORDER = ['blood_glucose', 'blood_pressure', 'heart_rate', 'spo2', 'blood_lipid', 'weight']

function appointmentTime(appointment: AppointmentItem): number {
  const time = Date.parse(appointment.due_at)
  return Number.isNaN(time) ? 0 : time
}

function formatAppointmentTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('month')}月${get('day')}日 ${get('hour')}:${get('minute')}`
}

function appointmentHeading(appointment: AppointmentItem): string {
  const { department, title } = appointment
  if (department && !title.includes(department)) return `${department} · ${title}`
  return title
}

function tileValue(r: HealthRecordItem): { value: string; unit: string } {
  if (r.record_type === 'blood_pressure' && r.extra_data) {
    const sys = r.extra_data.systolic ?? r.value
    const dia = r.extra_data.diastolic
    return { value: dia != null ? `${sys}/${dia}` : `${sys}`, unit: r.unit }
  }
  return { value: String(r.value), unit: r.unit }
}

/** 监测页（规格 §6.2）。 */
export default function MonitorPage() {
  const { alerts: liveAlerts, resolveAlert } = useAlert()
  const { showToast } = useToast()

  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [kind, setKind] = useState<TrendKind>('glucose')
  const [days, setDays] = useState<7 | 30>(30)
  const [trendRecords, setTrendRecords] = useState<HealthRecordItem[]>([])
  const [records7, setRecords7] = useState<HealthRecordItem[]>([])
  const [resolvedAlerts, setResolvedAlerts] = useState<AlertItem[]>([])
  const [showResolved, setShowResolved] = useState(false)
  const [expandedType, setExpandedType] = useState<string | null>(null)

  const [appointments, setAppointments] = useState<AppointmentItem[]>([])
  const [appointmentsLoading, setAppointmentsLoading] = useState(true)
  const [appointmentsError, setAppointmentsError] = useState(false)
  const [appointmentBusyId, setAppointmentBusyId] = useState<number | null>(null)

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const dash = await healthApi.getDashboard()
      setDashboard(dash.data as Dashboard)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadResolved = useCallback(async () => {
    try {
      const { data } = await featureApi.listAlerts(false)
      setResolvedAlerts((data as AlertItem[]).filter((a) => a.is_resolved))
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    void loadDashboard()
    void loadResolved()
  }, [loadDashboard, loadResolved])

  const loadAppointments = useCallback(async (silent = false) => {
    if (!silent) setAppointmentsLoading(true)
    setAppointmentsError(false)
    try {
      const { data } = await appointmentApi.list('pending')
      const list = ((data as AppointmentItem[]) ?? []).slice()
      list.sort((a, b) => appointmentTime(a) - appointmentTime(b))
      setAppointments(list)
    } catch {
      if (!silent) setAppointmentsError(true)
    } finally {
      if (!silent) setAppointmentsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAppointments()
  }, [loadAppointments])

  useEffect(() => {
    healthApi
      .listRecords({ days })
      .then((res) => setTrendRecords(res.data as HealthRecordItem[]))
      .catch(() => setTrendRecords([]))
  }, [days])

  useEffect(() => {
    healthApi
      .listRecords({ days: 7 })
      .then((res) => setRecords7(res.data as HealthRecordItem[]))
      .catch(() => setRecords7([]))
  }, [])

  const todayLatest = useMemo(() => {
    const recs = dashboard?.today_records ?? []
    const map = new Map<string, HealthRecordItem>()
    for (const r of recs) {
      const prev = map.get(r.record_type)
      if (!prev || r.recorded_at > prev.recorded_at) map.set(r.record_type, r)
    }
    return TILE_ORDER.map((t) => map.get(t)).filter((r): r is HealthRecordItem => Boolean(r))
  }, [dashboard])

  const unresolvedSorted = useMemo(
    () =>
      [...liveAlerts].sort(
        (a, b) =>
          (LEVEL_ORDER[b.level] ?? 0) - (LEVEL_ORDER[a.level] ?? 0) ||
          b.created_at.localeCompare(a.created_at),
      ),
    [liveAlerts],
  )

  const chartRecords = useMemo(
    () =>
      trendRecords.filter((r) =>
        kind === 'glucose' ? r.record_type === 'blood_glucose' : r.record_type === 'blood_pressure',
      ),
    [trendRecords, kind],
  )

  const expandedRecords = useMemo(() => {
    if (!expandedType) return []
    return records7
      .filter((r) => r.record_type === expandedType)
      .sort((a, b) => a.recorded_at.localeCompare(b.recorded_at))
      .slice(-7)
  }, [records7, expandedType])

  const handleResolve = async (id: number) => {
    await resolveAlert(id)
    void loadResolved()
  }

  const handleAppointment = async (id: number, status: 'done' | 'cancelled') => {
    setAppointmentBusyId(id)
    try {
      await appointmentApi.update(id, status)
      setAppointments((prev) => prev.filter((item) => item.id !== id))
      void loadAppointments(true)
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setAppointmentBusyId(null)
    }
  }

  if (loading) {
    return (
      <div className="px-5 py-8 text-center">
        <span className="t-body text-ink-soft">正在加载健康数据…</span>
      </div>
    )
  }

  if (error || !dashboard) {
    return (
      <div className="px-5 py-5">
        <div className="rounded-card bg-white p-5 text-center shadow-card">
          <p className="t-body text-ink-soft">健康数据加载失败，请稍后重试</p>
          <button
            type="button"
            onClick={() => void loadDashboard()}
            className="btn btn-primary mt-4"
            style={{ minHeight: 48 }}
          >
            重新加载
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <RiskCard level={dashboard.risk_level} copy={RISK_COPY[dashboard.risk_level] ?? RISK_COPY.green} />

      <SectionCard title="近期待办">
        {appointmentsLoading ? (
          <p className="t-body py-2 text-ink-soft">正在加载复诊安排…</p>
        ) : appointmentsError ? (
          <div className="py-2 text-center">
            <p className="t-body text-ink-soft">复诊安排加载失败，请稍后重试</p>
            <button
              type="button"
              onClick={() => void loadAppointments()}
              className="btn btn-primary mt-4"
              style={{ minHeight: 48 }}
            >
              重试
            </button>
          </div>
        ) : appointments.length === 0 ? (
          <p className="t-body py-2 text-ink-soft">暂无复诊安排</p>
        ) : (
          <div className="space-y-3">
            {appointments.map((appointment) => (
              <div key={appointment.id} className="rounded-btn border border-line bg-mist/60 p-4">
                <h3 className="t-h2">{appointmentHeading(appointment)}</h3>
                <p className="t-cap mt-1 text-ink-soft">{formatAppointmentTime(appointment.due_at)}</p>

                {appointment.source_document_id != null ? (
                  <Link
                    to={`/record/document/${appointment.source_document_id}`}
                    className="t-cap mt-1 inline-flex min-h-[48px] items-center text-primary-deep underline"
                  >
                    来自病历/处方
                  </Link>
                ) : (
                  <p className="t-cap mt-1 text-ink-soft">来自病历/处方</p>
                )}

                <div className="mt-3 flex gap-3">
                  <button
                    type="button"
                    onClick={() => void handleAppointment(appointment.id, 'done')}
                    disabled={appointmentBusyId === appointment.id}
                    className="btn btn-primary flex-1"
                    style={{ minHeight: 48 }}
                  >
                    完成了
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleAppointment(appointment.id, 'cancelled')}
                    disabled={appointmentBusyId === appointment.id}
                    className="btn btn-ghost flex-1"
                    style={{ minHeight: 48 }}
                  >
                    取消
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <section>
        <h2 className="t-h2 mb-3">今日指标</h2>
        {todayLatest.length === 0 ? (
          <p className="t-body text-ink-soft">今日未记录</p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {todayLatest.map((r) => {
              const { value, unit } = tileValue(r)
              return (
                <MetricTile
                  key={r.record_type}
                  label={formatRecordLabel(r)}
                  value={value}
                  unit={unit}
                  abnormal={r.is_abnormal}
                  time={formatDateTime(r.recorded_at)}
                  expanded={expandedType === r.record_type}
                  onClick={() =>
                    setExpandedType((prev) => (prev === r.record_type ? null : r.record_type))
                  }
                />
              )
            })}
          </div>
        )}

        {/* SPEC-GAP：规格为「展开 7 天小趋势」，此处以近 7 天数值列表最小实现 */}
        {expandedType && (
          <div className="mt-3 rounded-card bg-white p-4 shadow-card">
            <p className="t-cap text-ink-soft">
              {RECORD_TYPE_LABELS[expandedType] ?? expandedType} · 近 7 天
            </p>
            {expandedRecords.length === 0 ? (
              <p className="t-cap mt-2 text-ink-soft">暂无记录</p>
            ) : (
              <div className="mt-2 space-y-1">
                {expandedRecords.map((r) => (
                  <div key={r.id} className="flex justify-between">
                    <span className="t-cap text-ink-soft">{formatDateTime(r.recorded_at)}</span>
                    <span className="t-body">{tileValue(r).value} {r.unit}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="t-h2">健康趋势</h2>
          <div className="flex gap-2">
            <div className="flex rounded-full border border-line bg-white p-1">
              {(['glucose', 'bp'] as TrendKind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  aria-pressed={kind === k}
                  className={`t-cap rounded-full px-3 py-2 ${kind === k ? 'bg-primary/10 text-primary-deep' : 'text-ink-soft'}`}
                >
                  {k === 'glucose' ? '血糖' : '血压'}
                </button>
              ))}
            </div>
            <div className="flex rounded-full border border-line bg-white p-1">
              {([7, 30] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDays(d)}
                  aria-pressed={days === d}
                  className={`t-cap rounded-full px-3 py-2 ${days === d ? 'bg-primary/10 text-primary-deep' : 'text-ink-soft'}`}
                >
                  {d}天
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="rounded-card bg-white p-2 shadow-card">
          <TrendChart records={chartRecords} kind={kind} />
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="t-h2">预警提醒</h2>
          {resolvedAlerts.length > 0 && (
            <button
              type="button"
              onClick={() => setShowResolved((v) => !v)}
              className="t-cap text-primary-deep underline"
            >
              {showResolved ? '收起已处理' : '查看已处理'}
            </button>
          )}
        </div>

        {unresolvedSorted.length === 0 ? (
          <p className="t-body text-ink-soft">暂无未处理预警</p>
        ) : (
          <div className="space-y-3">
            {unresolvedSorted.map((a) => (
              <AlertListItem key={a.id} alert={a} onResolve={() => void handleResolve(a.id)} />
            ))}
          </div>
        )}

        {showResolved && resolvedAlerts.length > 0 && (
          <div className="mt-3 space-y-3">
            {resolvedAlerts.map((a) => (
              <AlertListItem key={`r${a.id}`} alert={a} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
