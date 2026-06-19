import { useEffect, useState } from 'react'
import { featureApi } from '../api/client'

const levelStyles: Record<string, string> = {
  green: 'border-safe bg-green-50',
  yellow: 'border-warn bg-yellow-50',
  orange: 'border-orange-500 bg-orange-50',
  red: 'border-danger bg-red-50',
}

const levelLabels: Record<string, string> = {
  green: '低风险',
  yellow: '关注',
  orange: '警告',
  red: '危险',
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)

  const loadAlerts = () => {
    featureApi.listAlerts()
      .then((res) => setAlerts(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadAlerts() }, [])

  const handleResolve = async (id: number) => {
    await featureApi.resolveAlert(id)
    loadAlerts()
  }

  const handleRead = async (id: number) => {
    await featureApi.markAlertRead(id)
    loadAlerts()
  }

  if (loading) return <div className="text-center py-10 text-gray-400">加载中...</div>

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">系统根据您的健康指标实时监测，异常时自动触发分级预警</p>

      {alerts.length === 0 ? (
        <div className="bg-white rounded-2xl p-8 text-center shadow-sm">
          <div className="text-4xl mb-2">✅</div>
          <p className="text-gray-500">暂无预警，您的指标整体稳定</p>
        </div>
      ) : (
        alerts.map((alert) => (
          <div
            key={alert.id as number}
            className={`bg-white rounded-2xl p-4 shadow-sm border-l-4 ${levelStyles[alert.level as string] || ''}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-white">
                  {levelLabels[alert.level as string]}
                </span>
                <h3 className="font-semibold mt-2">{alert.title as string}</h3>
                <p className="text-sm text-gray-600 mt-1">{alert.message as string}</p>
                {alert.suggestion ? (
                  <p className="text-sm text-primary mt-2">建议：{String(alert.suggestion)}</p>
                ) : null}
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              {!alert.is_read && (
                <button
                  onClick={() => handleRead(alert.id as number)}
                  className="text-xs px-3 py-1 border rounded-full text-gray-600"
                >
                  标记已读
                </button>
              )}
              {!alert.is_resolved && (
                <button
                  onClick={() => handleResolve(alert.id as number)}
                  className="text-xs px-3 py-1 bg-primary text-white rounded-full"
                >
                  已处理
                </button>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
