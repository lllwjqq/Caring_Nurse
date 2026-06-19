import { useEffect, useRef, useState } from 'react'
import { agentApi } from '../api/client'
import AgentTraceView from '../components/AgentTrace'

interface Message {
  role: 'user' | 'assistant'
  content: string
  traces?: Array<{ agent: string; action: string; duration_ms: number }>
}

const QUICK_QUESTIONS = [
  '最近头晕怎么办？',
  '请为我制定管理方案',
  '帮我分析一下最近的数据',
  '查看当前预警情况',
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '您好！我是贴心小护士，可以帮您解答慢病管理问题、分析健康数据、制定管理方案。有什么可以帮您的？' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string>()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return
    setMessages((m) => [...m, { role: 'user', content: text }])
    setInput('')
    setLoading(true)

    try {
      const { data } = await agentApi.chat(text, sessionId)
      setSessionId(data.session_id)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: data.reply, traces: data.agent_traces },
      ])
    } catch {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: '抱歉，服务暂时不可用，请稍后重试。' },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col" style={{ minHeight: 'calc(100vh - 140px)' }}>
      <div className="flex-1 space-y-3 overflow-y-auto pb-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-primary text-white rounded-br-md'
                  : 'bg-white shadow-sm rounded-bl-md'
              }`}
            >
              {msg.content}
              {msg.traces && <AgentTraceView traces={msg.traces} />}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white shadow-sm rounded-2xl px-4 py-3 text-sm text-gray-400">
              小护士正在思考...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2 overflow-x-auto py-2">
        {QUICK_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => sendMessage(q)}
            className="whitespace-nowrap px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs text-gray-600"
          >
            {q}
          </button>
        ))}
      </div>

      <div className="flex gap-2 pt-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage(input)}
          placeholder="输入您的问题..."
          className="flex-1 px-4 py-3 border border-gray-200 rounded-xl bg-white"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading}
          className="bg-primary text-white px-5 py-3 rounded-xl font-medium disabled:opacity-50"
        >
          发送
        </button>
      </div>
    </div>
  )
}
