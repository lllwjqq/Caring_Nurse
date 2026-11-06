import ReactECharts from 'echarts-for-react'
import type { HealthRecordItem } from '../constants/healthRecords'

export type TrendKind = 'glucose' | 'bp'

const AXIS_LABEL = { fontSize: 16, color: '#1B2A3A' }
const LEGEND_TEXT = { fontSize: 16, color: '#1B2A3A' }

/** 健康趋势折线图（规格 §3.4 / §6.2）。图表文字统一 ≥16px。 */
export default function TrendChart({ records, kind }: { records: HealthRecordItem[]; kind: TrendKind }) {
  if (!records.length) {
    return <div className="t-body py-8 text-center text-ink-soft">暂无数据，先记录一次</div>
  }

  const sorted = [...records].sort((a, b) => a.recorded_at.localeCompare(b.recorded_at))
  const x = sorted.map((r) => r.recorded_at.slice(5, 10))

  const common: any = {
    grid: { top: 28, right: 16, bottom: 44, left: 52 },
    tooltip: { trigger: 'axis', textStyle: { fontSize: 16 } },
    xAxis: { type: 'category', data: x, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#E6EDF5' } } },
    yAxis: {
      type: 'value',
      axisLabel: AXIS_LABEL,
      splitLine: { lineStyle: { color: '#E6EDF5' } },
    },
  }

  const option: any =
    kind === 'glucose'
      ? {
          ...common,
          series: [
            {
              name: '血糖',
              type: 'line',
              smooth: true,
              symbolSize: 8,
              data: sorted.map((r) => r.value),
              itemStyle: { color: '#4A90D9' },
              lineStyle: { width: 3 },
              markArea: {
                silent: true,
                itemStyle: { color: 'rgba(74,144,217,0.08)' },
                data: [[{ yAxis: 4.4 }, { yAxis: 7.0 }]],
              },
            },
          ],
        }
      : {
          ...common,
          legend: { bottom: 0, textStyle: LEGEND_TEXT },
          series: [
            {
              name: '收缩压',
              type: 'line',
              smooth: true,
              symbolSize: 8,
              data: sorted.map((r) => r.extra_data?.systolic ?? r.value),
              itemStyle: { color: '#FF6B8A' },
              lineStyle: { width: 3 },
            },
            {
              name: '舒张压',
              type: 'line',
              smooth: true,
              symbolSize: 8,
              data: sorted.map((r) => r.extra_data?.diastolic ?? r.value),
              itemStyle: { color: '#F2A65A' },
              lineStyle: { width: 3 },
            },
          ],
        }

  return <ReactECharts option={option} style={{ height: 240 }} notMerge />
}
