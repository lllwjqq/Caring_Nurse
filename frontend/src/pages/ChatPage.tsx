import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { agentApi, voiceApi } from '../api/client'
import AgentTraceView from '../components/AgentTrace'
import { startAudioRecording } from '../lib/audio'

interface Trace {
  agent: string
  action: string
  duration_ms: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  traces?: Trace[]
}

const QUICK_QUESTIONS = [
  '最近头晕怎么办？',
  '请为我制定管理方案',
  '帮我分析一下最近的数据',
  '查看当前预警情况',
]

const CHAT_SESSION_KEY = 'chat_session_id'

// 输入框自动增高的上限（约 6 行），超过后输入框内部滚动
const MAX_INPUT_HEIGHT = 150

// TTS 音频缓存（文本 → Blob），重复播放同一句免走接口
const ttsCache = new Map<string, Blob>()

const WELCOME_MESSAGE: Message = {
  role: 'assistant',
  content: '您好！我是贴心小护士，可以帮您解答慢病管理问题。您可以打字提问，也可以按住下方按钮说话。',
}

interface SessionSummary {
  session_id: string
  title: string
  message_count: number
  last_message_at: string
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE])
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [recording, setRecording] = useState(false)
  const [recognizing, setRecognizing] = useState(false)
  const [speakingIdx, setSpeakingIdx] = useState<number | null>(null)
  const [synthingIdx, setSynthingIdx] = useState<number | null>(null)
  const [sessionId, setSessionId] = useState<string>()
  const [chatHeight, setChatHeight] = useState<number>()
  const containerRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const recorderRef = useRef<{ stop: () => Promise<Blob> } | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 固定整体高度：仅对话区内部滚动。容器高度 = 视口高度 - 容器顶部 - 底部预留
  // （底部预留 80px = 底部导航 pb-16 64px + main 下内边距 py-4 16px）。
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => {
      const viewport = window.visualViewport?.height ?? window.innerHeight
      const top = el.getBoundingClientRect().top
      setChatHeight(Math.max(280, viewport - top - 80))
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  // 输入框随内容自动增高，到达上限后内部滚动
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_INPUT_HEIGHT)}px`
  }, [input])

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    setSpeakingIdx(null)
  }

  const loadSessions = async () => {
    try {
      const { data } = await agentApi.listSessions()
      setSessions(data as SessionSummary[])
    } catch {
      /* ignore */
    }
  }

  const switchSession = async (sid: string) => {
    try {
      const { data } = await agentApi.getSessionMessages(sid)
      const msgs: Message[] = (data as { role: string; content: string }[]).map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      setSessionId(sid)
      localStorage.setItem(CHAT_SESSION_KEY, sid)
      setMessages(msgs.length ? msgs : [WELCOME_MESSAGE])
    } catch {
      /* ignore */
    }
  }

  const startNewChat = () => {
    stopAudio()
    localStorage.removeItem(CHAT_SESSION_KEY)
    setSessionId(undefined)
    setMessages([WELCOME_MESSAGE])
  }

  const deleteSession = async (sid: string) => {
    if (!window.confirm('确认删除该对话？删除后无法恢复。')) return
    try {
      await agentApi.deleteSession(sid)
    } catch {
      alert('删除失败，请重试')
      return
    }
    const { data } = await agentApi.listSessions()
    const list = data as SessionSummary[]
    setSessions(list)
    // 删除的是当前会话 → 回到空白新对话
    if (sid === sessionId) {
      stopAudio()
      localStorage.removeItem(CHAT_SESSION_KEY)
      setSessionId(undefined)
      setMessages([WELCOME_MESSAGE])
    }
  }

  // 进入页面时恢复上次会话（短时记忆）
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const { data } = await agentApi.listSessions()
      if (cancelled) return
      const list = data as SessionSummary[]
      setSessions(list)
      if (!list.length) return
      const stored = localStorage.getItem(CHAT_SESSION_KEY)
      const target = list.find((s) => s.session_id === stored) || list[0]
      await switchSession(target.session_id)
    })().catch(() => {})
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const speak = async (text: string, idx: number) => {
    stopAudio()
    setSynthingIdx(idx)
    try {
      let blob = ttsCache.get(text)
      if (!blob) {
        const { data } = await voiceApi.tts(text)
        blob = data as Blob
        ttsCache.set(text, blob)
      }
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      setSynthingIdx(null)
      setSpeakingIdx(idx)
      audio.onended = () => {
        setSpeakingIdx(null)
        URL.revokeObjectURL(url)
      }
      audio.onerror = () => {
        setSpeakingIdx(null)
        URL.revokeObjectURL(url)
      }
      await audio.play()
    } catch {
      setSynthingIdx(null)
      setSpeakingIdx(null)
    }
  }

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return
    setInput('')
    setLoading(true)

    const assistantIdx = messages.length + 1
    setMessages((m) => [
      ...m,
      { role: 'user', content: text },
      { role: 'assistant', content: '', streaming: true },
    ])

    let content = ''
    const traces: Trace[] = []
    let ok = true

    try {
      for await (const event of agentApi.chatStream(text, sessionId)) {
        if (event.type === 'token') {
          content += event.data
          setMessages((m) => {
            const copy = [...m]
            copy[assistantIdx] = { ...copy[assistantIdx], content }
            return copy
          })
        } else if (event.type === 'trace') {
          traces.push(event.data)
          setMessages((m) => {
            const copy = [...m]
            copy[assistantIdx] = { ...copy[assistantIdx], traces: [...traces] }
            return copy
          })
        } else if (event.type === 'done') {
          if (event.session_id) {
            setSessionId(event.session_id)
            localStorage.setItem(CHAT_SESSION_KEY, event.session_id)
            loadSessions()
          }
        }
      }
    } catch {
      ok = false
      content = '抱歉，服务暂时不可用，请稍后重试。'
    } finally {
      setMessages((m) => {
        const copy = [...m]
        copy[assistantIdx] = { ...copy[assistantIdx], content, streaming: false, traces }
        return copy
      })
      setLoading(false)
    }

    if (ok && content) speak(content, assistantIdx)
  }

  const startRecording = async () => {
    if (loading || recording) return
    try {
      recorderRef.current = await startAudioRecording()
      setRecording(true)
    } catch {
      alert('无法访问麦克风，请允许麦克风权限或改用文字输入')
    }
  }

  const stopRecording = async () => {
    if (!recorderRef.current) return
    setRecording(false)
    setRecognizing(true)
    try {
      const blob = await recorderRef.current.stop()
      recorderRef.current = null
      const { data } = await voiceApi.transcribe(blob)
      const text = data?.text?.trim()
      if (text) {
        // 识别结果先填入输入框，由用户确认/编辑后再发送
        setInput((prev) => (prev.trim() ? `${prev} ${text}` : text))
      } else {
        alert('没有听清，请再说一次')
      }
    } catch {
      alert('语音识别失败，请改用文字输入')
    } finally {
      setRecognizing(false)
    }
  }

  return (
    <div
      ref={containerRef}
      className="flex flex-col overflow-hidden"
      style={{ height: chatHeight }}
    >
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        <button
          onClick={startNewChat}
          className="shrink-0 px-3 py-1.5 bg-primary text-white rounded-full text-sm font-medium"
        >
          + 新对话
        </button>
        {sessions.map((s) => {
          const active = s.session_id === sessionId
          return (
            <div
              key={s.session_id}
              className={`shrink-0 flex items-center max-w-[160px] rounded-full text-sm border ${
                active ? 'bg-primary/10 border-primary' : 'bg-white border-gray-200'
              }`}
            >
              <button
                onClick={() => switchSession(s.session_id)}
                className={`truncate pl-3 py-1.5 ${active ? 'text-primary' : 'text-gray-600'}`}
              >
                {s.title || '对话'}
              </button>
              <button
                onClick={() => deleteSession(s.session_id)}
                title="删除对话"
                className="px-2 py-1.5 text-gray-400 hover:text-red-500"
              >
                ×
              </button>
            </div>
          )
        })}
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto pb-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-base whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-primary text-white rounded-br-md'
                  : 'bg-white shadow-sm rounded-bl-md'
              }`}
            >
              {msg.content}
              {msg.streaming && <span className="text-gray-400">…</span>}
              {msg.traces && msg.traces.length > 0 && <AgentTraceView traces={msg.traces} />}
              {msg.role === 'assistant' && msg.content && !msg.streaming && (
                <button
                  onClick={() =>
                    speakingIdx === i ? stopAudio() : speak(msg.content, i)
                  }
                  disabled={synthingIdx === i}
                  className="mt-2 text-sm text-primary font-medium disabled:opacity-50"
                >
                  {speakingIdx === i ? '停止播放' : synthingIdx === i ? '合成中…' : '播放语音'}
                </button>
              )}
            </div>
          </div>
        ))}
        {loading && !recording && (
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
            className="whitespace-nowrap px-3 py-1.5 bg-white border border-gray-200 rounded-full text-sm text-gray-600"
          >
            {q}
          </button>
        ))}
      </div>

      <div className="flex gap-2 pt-2 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              sendMessage(input)
            }
          }}
          rows={1}
          placeholder="输入您的问题...（Shift+Enter 换行）"
          className="flex-1 px-4 py-3 border border-gray-200 rounded-xl bg-white text-base resize-none overflow-y-auto"
          style={{ maxHeight: MAX_INPUT_HEIGHT }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading}
          className="bg-primary text-white px-5 py-3 rounded-xl font-medium disabled:opacity-50"
        >
          发送
        </button>
      </div>

      <div className="pt-3 pb-1">
        <button
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={() => recording && stopRecording()}
          onTouchStart={(e) => {
            e.preventDefault()
            startRecording()
          }}
          onTouchEnd={(e) => {
            e.preventDefault()
            stopRecording()
          }}
          disabled={loading}
          className={`w-full py-4 rounded-2xl text-lg font-semibold transition-colors disabled:opacity-50 ${
            recording
              ? 'bg-red-500 text-white'
              : recognizing
                ? 'bg-amber-500 text-white'
                : 'bg-primary text-white'
          }`}
        >
          {recording ? '正在聆听… 松开结束' : recognizing ? '正在识别…' : '按住说话'}
        </button>
      </div>
    </div>
  )
}
