import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { knowledgeApi } from '../api/client'

export default function KnowledgePage() {
  const [graph, setGraph] = useState<{ nodes: Array<Record<string, string>>; edges: Array<Record<string, string>> } | null>(null)

  useEffect(() => {
    knowledgeApi.getGraph().then((res) => setGraph(res.data))
  }, [])

  if (!graph) return <div className="text-center py-10 text-gray-400">加载中...</div>

  const typeColors: Record<string, string> = {
    disease: '#4A90D9',
    symptom: '#FF6B8A',
    treatment: '#52C41A',
    diet: '#FAAD14',
  }

  const option = {
    tooltip: {},
    legend: { data: ['疾病', '症状', '治疗', '饮食'], bottom: 0 },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      label: { show: true, fontSize: 10 },
      force: { repulsion: 200, edgeLength: 80 },
      categories: [
        { name: '疾病' },
        { name: '症状' },
        { name: '治疗' },
        { name: '饮食' },
      ],
      data: graph.nodes.map((n) => ({
        id: n.id,
        name: n.label,
        category: n.type === 'disease' ? 0 : n.type === 'symptom' ? 1 : n.type === 'treatment' ? 2 : 3,
        symbolSize: n.type === 'disease' ? 40 : 25,
        itemStyle: { color: typeColors[n.type] || '#999' },
      })),
      links: graph.edges.map((e) => ({
        source: e.source,
        target: e.target,
        lineStyle: { curveness: 0.2 },
      })),
    }],
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">慢病领域知识图谱：整合疾病、症状、治疗方案与饮食建议</p>
      <div className="bg-white rounded-2xl p-2 shadow-sm">
        <ReactECharts option={option} style={{ height: 400 }} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(typeColors).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2 text-sm">
            <div className="w-3 h-3 rounded-full" style={{ background: color }} />
            <span className="text-gray-600">
              {type === 'disease' ? '疾病' : type === 'symptom' ? '症状' : type === 'treatment' ? '治疗' : '饮食'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
