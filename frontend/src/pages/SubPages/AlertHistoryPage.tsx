import { useCallback, useEffect, useMemo, useState } from 'react'
import { featureApi } from '../../api/client'
import { useAlert } from '../../context/AlertContext'
import { formatDateTime } from '../../constants/healthRecords'
import type { AlertItem } from '../../lib/types'

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'red', label: '红' },
  { key: 'orange', label: '橙' },
  { key: 'yellow', label: '黄' },
]

const LEVEL_STYLE: Record<string, { bar: string; pill: string; label: string }> = {
  red: { bar: 'border-l-level-red', pill: 'bg-level-red text-white', label: '严重' },
  orange: { bar: 'border-l-level-orange', pill: 'bg-level-orange text-white', label: '警告' },
  yellow: { bar: 'border-l-warn', pill: 'bg-level-yellow text-level-yellow-ink', label: '关注' },
  green: { bar: 'border-l-level-green', pill: 'bg-level-green text-white', label: '提示' },
}

/** 预警记录子页（规格 §6.5.3）。 */
export default function AlertHistoryPage() {
  const { resolveAlert } = useAlert()
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await featureApi.listAlerts(false)
      setAlerts(data as AlertItem[])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(
    () => (filter === 'all' ? alerts : alerts.filter((a) => a.level === filter)),
    [alerts, filter],
  )

  const handleResolve = async (id: number) => {
    await resolveAlert(id)
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_resolved: true } : a)))
  }

  if (loading) {
    return (
      <div className="px-5 py-8 text-center">
        <span className="t-body text-ink-soft">正在加载预警记录…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="px-5 py-5">
        <div className="rounded-card bg-white p-5 text-center shadow-card">
          <p className="t-body text-ink-soft">预警记录加载失败</p>
          <button
            type="button"
            onClick={() => void load()}
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
    <div className="space-y-4 px-5 py-5">
      <div className="flex gap-2 overflow-x-auto">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
            className={`t-cap shrink-0 rounded-full border px-4 ${
              filter === f.key ? 'bg-primary-deep text-white' : 'border-line bg-white text-ink-soft'
            }`}
            style={{ minHeight: 48 }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="t-body text-ink-soft">暂无预警记录</p>
      ) : (
        <div className="space-y-3">
          {filtered.map((a) => {
            const meta = LEVEL_STYLE[a.level] ?? LEVEL_STYLE.yellow
            const open = expanded === a.id
            return (
              <div
                key={a.id}
                className={`overflow-hidden rounded-btn border-l-4 bg-white shadow-card ${meta.bar}`}
              >
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : a.id)}
                  aria-expanded={open}
                  className="w-full p-4 text-left"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="t-h2">{a.title}</span>
                    <span className="t-cap shrink-0 text-ink-soft">
                      {formatDateTime(a.created_at)}
                    </span>
                  </div>
                  <p className="t-body mt-1 text-ink-soft">{a.message}</p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className={`t-cap rounded-full px-2 py-0.5 ${meta.pill}`}>
                      {a.level_label || meta.label}
                    </span>
                    <span className="t-cap text-ink-soft">来源：{a.source_label || '系统'}</span>
                    <span className="t-cap text-ink-soft">{a.is_resolved ? '已处理' : '未处理'}</span>
                  </div>
                </button>

                {open && (
                  <div className="border-t border-line px-4 pb-4 pt-3">
                    <p className="t-cap text-ink-soft">处理建议</p>
                    <p className="t-body mt-1">{a.suggestion || '请结合医生意见处理，并继续监测。'}</p>
                    {!a.is_resolved && (
                      <button
                        type="button"
                        onClick={() => void handleResolve(a.id)}
                        className="btn btn-primary mt-3"
                        style={{ minHeight: 48 }}
                      >
                        标记已处理
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
