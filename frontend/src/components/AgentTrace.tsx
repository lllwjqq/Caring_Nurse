interface AgentTrace {
  agent: string
  action: string
  duration_ms: number
  output_summary?: string
}

const agentColors: Record<string, string> = {
  router: 'bg-purple-100 text-purple-700',
  consult: 'bg-blue-100 text-blue-700',
  monitor: 'bg-green-100 text-green-700',
  planner: 'bg-orange-100 text-orange-700',
  followup: 'bg-cyan-100 text-cyan-700',
  warning: 'bg-red-100 text-red-700',
}

const agentLabels: Record<string, string> = {
  router: '路由Agent',
  consult: '问诊Agent',
  monitor: '监测Agent',
  planner: '方案Agent',
  followup: '随访Agent',
  warning: '预警Agent',
}

export default function AgentTraceView({ traces }: { traces: AgentTrace[] }) {
  if (!traces.length) return null

  return (
    <div className="bg-gray-50 rounded-xl p-3 mt-3">
      <h4 className="text-sm font-semibold text-gray-600 mb-2">Agent 协作链路</h4>
      <div className="space-y-2">
        {traces.map((t, i) => (
          <div key={i} className="flex items-center gap-2">
            {i > 0 && <span className="text-gray-300 text-xs">→</span>}
            <div className={`px-2 py-1 rounded-lg text-xs ${agentColors[t.agent] || 'bg-gray-100'}`}>
              <span className="font-medium">{agentLabels[t.agent] || t.agent}</span>
              <span className="text-gray-500 ml-1">({t.duration_ms}ms)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
