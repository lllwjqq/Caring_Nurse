import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import { healthApi } from '../api/client'

const riskColors: Record<string, string> = {
  green: 'bg-safe',
  yellow: 'bg-warn',
  orange: 'bg-orange-500',
  red: 'bg-danger',
}

const riskLabels: Record<string, string> = {
  green: '稳定',
  yellow: '关注',
  orange: '警告',
  red: '危险',
}

export default function DashboardPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    healthApi.getDashboard()
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center py-10 text-gray-400">加载中...</div>
  if (!data) return <div className="text-center py-10 text-gray-400">暂无数据</div>

  const trends = (data.trends as Record<string, Array<{ date: string; value: number }>>) || {}
  const glucoseTrend = trends.blood_glucose || []
  const bpTrend = trends.blood_pressure || []

  const chartOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['血糖', '收缩压'], bottom: 0 },
    grid: { top: 30, right: 20, bottom: 40, left: 40 },
    xAxis: {
      type: 'category',
      data: glucoseTrend.map((d) => d.date.slice(5, 10)),
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: '血糖',
        type: 'line',
        smooth: true,
        data: glucoseTrend.map((d) => d.value),
        itemStyle: { color: '#4A90D9' },
      },
      {
        name: '收缩压',
        type: 'line',
        smooth: true,
        data: bpTrend.map((d) => (d as unknown as Record<string, number>).systolic || d.value),
        itemStyle: { color: '#FF6B8A' },
      },
    ],
  }

  const todayRecords = (data.today_records as Array<Record<string, unknown>>) || []
  const recentAlerts = (data.recent_alerts as Array<Record<string, unknown>>) || []

  return (
    <div className="space-y-4">
      <div className={`rounded-2xl p-4 text-white ${riskColors[data.risk_level as string] || 'bg-safe'}`}>
        <div className="flex justify-between items-center">
          <div>
            <p className="text-sm opacity-80">当前风险等级</p>
            <p className="text-2xl font-bold">{riskLabels[data.risk_level as string] || '稳定'}</p>
          </div>
          <div className="text-right">
            <p className="text-sm opacity-80">待办随访</p>
            <p className="text-2xl font-bold">{data.pending_followups as number}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Link to="/records" className="bg-white rounded-xl p-4 shadow-sm text-center">
          <div className="text-2xl">📝</div>
          <p className="text-sm mt-1">数据录入</p>
        </Link>
        <Link to="/chat" className="bg-white rounded-xl p-4 shadow-sm text-center">
          <div className="text-2xl">💬</div>
          <p className="text-sm mt-1">智能问诊</p>
        </Link>
        <Link to="/followups" className="bg-white rounded-xl p-4 shadow-sm text-center">
          <div className="text-2xl">📋</div>
          <p className="text-sm mt-1">随访任务</p>
        </Link>
        <Link to="/documents" className="bg-white rounded-xl p-4 shadow-sm text-center">
          <div className="text-2xl">📄</div>
          <p className="text-sm mt-1">报告上传</p>
        </Link>
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <h3 className="font-semibold mb-3">健康趋势</h3>
        {glucoseTrend.length > 0 ? (
          <ReactECharts option={chartOption} style={{ height: 220 }} />
        ) : (
          <p className="text-gray-400 text-sm text-center py-8">暂无趋势数据，请先录入健康指标</p>
        )}
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-semibold">今日指标</h3>
          <Link to="/records" className="text-primary text-sm">录入</Link>
        </div>
        {todayRecords.length === 0 ? (
          <p className="text-gray-400 text-sm">今日尚未录入数据</p>
        ) : (
          <div className="space-y-2">
            {todayRecords.map((r, i) => (
              <div key={i} className="flex justify-between items-center py-2 border-b border-gray-50 last:border-0">
                <span className="text-sm text-gray-600">{r.record_type as string}</span>
                <span className={`font-medium ${r.is_abnormal ? 'text-danger' : ''}`}>
                  {r.value as number}{r.unit as string}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {recentAlerts.length > 0 && (
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold">最新预警</h3>
            <Link to="/alerts" className="text-primary text-sm">查看全部</Link>
          </div>
          {recentAlerts.slice(0, 2).map((a, i) => (
            <div key={i} className="py-2 border-b border-gray-50 last:border-0">
              <p className="text-sm font-medium">{a.title as string}</p>
              <p className="text-xs text-gray-500 mt-1">{a.message as string}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
