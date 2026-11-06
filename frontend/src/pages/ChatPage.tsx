import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { agentApi } from '../api/client'
import AlertBubble from '../components/AlertBubble'
import MessageBubble from '../components/MessageBubble'
import { MicIcon, SendIcon } from '../components/icons'
import { useToast } from '../components/Toast'
import { useAlert } from '../context/AlertContext'
import { useVoice } from '../context/VoiceContext'
import { useVoiceRecorder } from '../lib/useVoiceRecorder'
import type { AgentAction, AgentEvidence, AgentPresentation, AlertItem } from '../lib/types'

interface ChatMsg {
  key: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  error?: boolean
  retryText?: string
  createdAt: string
  actions?: AgentAction[]
  evidence?: AgentEvidence[]
  presentation?: AgentPresentation
}

interface SessionSummary {
  session_id: string
  title: string
  message_count: number
  last_message_at: string
}

const QUICK_QUESTIONS = ['我头晕怎么办', '帮我记血糖', '查看当前预警', '请为我制定管理方案']

const WELCOME = '您好！我是贴心小护士，可以帮您解答慢病管理问题。您可以打字提问，也可以按住下方按钮说话。'

type TimelineItem =
  | { kind: 'msg'; msg: ChatMsg; createdAt: string }
  | { kind: 'alert'; alert: AlertItem; createdAt: string }

export default function ChatPage() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const voice = useVoice()
  const { alerts, markRead } = useAlert()
  const recorder = useVoiceRecorder()

  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingSession, setLoadingSession] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)
  const [speakingKey, setSpeakingKey] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(100)

  const sessionIdRef = useRef<string | undefined>(undefined)
  sessionIdRef.current = sessionId

  const bottomRef = useRef<HTMLDivElement>(null)

  /* ---------- 会话恢复 ---------- */
  const loadConversation = useCallback(async () => {
    setLoadingSession(true)
    setLoadError(false)
    try {
      const { data } = await agentApi.listSessions()
      const list = (data || []) as SessionSummary[]
      if (!list.length) {
        setMessages([])
        setSessionId(undefined)
        return
      }
      const sid = list[0].session_id
      const res = await agentApi.getSessionMessages(sid)
      const rows = (res.data || []) as Array<{ id: number; role: string; content: string; created_at: string }>
      setSessionId(sid)
      setMessages(
        rows.map((r) => ({
          key: `m${r.id}`,
          role: r.role === 'user' ? 'user' : 'assistant',
          content: r.content,
          createdAt: r.created_at,
        })),
      )
    } catch {
      setLoadError(true)
    } finally {
      setLoadingSession(false)
    }
  }, [])

  useEffect(() => {
    void loadConversation()
  }, [loadConversation])

  /* ---------- 滚动到底 ---------- */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, alerts.length, sending, loadingSession])

  /* ---------- 朗读 ---------- */
  useEffect(() => {
    if (!voice.speaking) setSpeakingKey(null)
  }, [voice.speaking])

  const toggleSpeak = (key: string, content: string) => {
    if (speakingKey === key) {
      voice.stop()
      setSpeakingKey(null)
      return
    }
    setSpeakingKey(key)
    void voice.speak(content).then((ok) => {
      if (!ok) {
        setSpeakingKey(null)
        showToast('语音播放失败，请稍后重试')
      }
    })
  }

  /* ---------- 发送 / 流式 ---------- */
  const streamReply = useCallback(
    async (text: string, asstKey: string) => {
      setSending(true)
      setMessages((prev) =>
        prev.map((m) => (m.key === asstKey ? { ...m, streaming: true, error: false, content: '' } : m)),
      )
      let acc = ''
      let actions: AgentAction[] = []
      let evidence: AgentEvidence[] = []
      let presentation: AgentPresentation | undefined
      try {
        for await (const ev of agentApi.chatStream(text, sessionIdRef.current)) {
          if (ev.type === 'token') {
            acc += String(ev.data ?? '')
            setMessages((prev) => prev.map((m) => (m.key === asstKey ? { ...m, content: acc } : m)))
          } else if (ev.type === 'action') {
            const action = ev.data as AgentAction
            actions = [...actions, action]
            setMessages((prev) => prev.map((m) => (m.key === asstKey ? { ...m, actions } : m)))
            if (
              action.type === 'record_created' ||
              action.type === 'reminder_created' ||
              action.type === 'safety_alert' ||
              action.type === 'toast'
            ) {
              showToast(action.summary || action.message || '操作完成')
            }
          } else if (ev.type === 'evidence') {
            evidence = [...evidence, ev.data as AgentEvidence]
            setMessages((prev) => prev.map((m) => (m.key === asstKey ? { ...m, evidence } : m)))
          } else if (ev.type === 'done') {
            if (ev.session_id) {
              sessionIdRef.current = String(ev.session_id)
              setSessionId(String(ev.session_id))
            }
            if (Array.isArray(ev.actions)) actions = ev.actions as AgentAction[]
            if (Array.isArray(ev.evidence)) evidence = ev.evidence as AgentEvidence[]
            if (ev.presentation && typeof ev.presentation === 'object') {
              presentation = ev.presentation as AgentPresentation
            }
          }
        }
        setMessages((prev) =>
          prev.map((m) =>
            m.key === asstKey
              ? { ...m, streaming: false, content: acc, actions, evidence, presentation }
              : m,
          ),
        )
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.key === asstKey
              ? { ...m, streaming: false, error: true, content: acc, actions, evidence, presentation }
              : m,
          ),
        )
      } finally {
        setSending(false)
      }
    },
    [showToast],
  )

  const sendMessage = (text: string) => {
    const content = text.trim()
    if (!content || sending) return
    setInput('')
    const stamp = new Date().toISOString()
    const userKey = `u${Date.now()}`
    const asstKey = `a${Date.now()}`
    setMessages((prev) => [
      ...prev,
      { key: userKey, role: 'user', content, createdAt: stamp },
      {
        key: asstKey,
        role: 'assistant',
        content: '',
        streaming: true,
        retryText: content,
        createdAt: new Date().toISOString(),
      },
    ])
    void streamReply(content, asstKey)
  }

  const retry = (msg: ChatMsg) => {
    if (!msg.retryText) return
    void streamReply(msg.retryText, msg.key)
  }

  /* ---------- 消费悬浮球转来的问诊文本 ---------- */
  // 悬浮球识别出的话若不是健康数据/用药，会排进 pendingTranscript；
  // 这里在会话加载完成后自动作为一条问诊消息发送，避免用户对着悬浮球
  // 说的问诊问题被丢掉（此前只提示「没太听清」）。
  useEffect(() => {
    if (loadingSession) return
    if (!voice.pendingTranscript) return
    const text = voice.takePendingTranscript()
    if (text) sendMessage(text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingSession, voice.pendingTranscript])

  /* ---------- 录音 ---------- */
  const handleVoiceDown = async () => {
    if (sending || recorder.recording) return
    try {
      await recorder.start()
    } catch {
      showToast('无法访问麦克风，请改用文字输入')
    }
  }

  const handleVoiceUp = async () => {
    if (!recorder.recording) return
    try {
      const text = await recorder.stop()
      if (!text) {
        showToast('没太听清，能再说一次吗？')
        return
      }
      // 健康参数/用药 → 全局确认卡；普通提问 → 回填输入框
      if (voice.processTranscript(text)) return
      setInput((prev) => (prev.trim() ? `${prev} ${text}` : text))
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      showToast(status === 503 ? '语音服务未配置' : '语音识别失败，请改用文字输入')
    }
  }

  /* ---------- 时间线合并（长对话只渲染最近 100 条） ---------- */
  const visibleMessages = useMemo(
    () => (messages.length > visibleCount ? messages.slice(-visibleCount) : messages),
    [messages, visibleCount],
  )

  const timeline = useMemo<TimelineItem[]>(() => {
    const items: TimelineItem[] = []
    for (const m of visibleMessages) items.push({ kind: 'msg', msg: m, createdAt: m.createdAt })
    // 已了解（is_read=true）的预警不再在对话流中展示，预警历史页仍可查看
    for (const a of alerts) {
      if (!a.is_read) items.push({ kind: 'alert', alert: a, createdAt: a.created_at })
    }
    items.sort((x, y) => (x.createdAt || '').localeCompare(y.createdAt || ''))
    return items
  }, [visibleMessages, alerts])

  return (
    <div className="flex h-full flex-col">
      {/* 对话流 */}
      <div className="flex-1 overflow-y-auto px-5 pb-3 pt-1">
        <div className="t-cap py-2 text-center text-ink-soft">今天</div>

        {loadingSession && (
          <div className="py-6 text-center">
            <span className="t-body text-ink-soft">正在加载对话…</span>
          </div>
        )}

        {loadError && !loadingSession && (
          <div className="rounded-card bg-white p-5 text-center shadow-card">
            <p className="t-body text-ink-soft">对话加载失败，请检查网络后重试</p>
            <button
              type="button"
              onClick={() => void loadConversation()}
              className="btn btn-primary mt-4"
              style={{ minHeight: 48 }}
            >
              重新加载
            </button>
          </div>
        )}

        {!loadingSession && !loadError && messages.length === 0 && (
          <div className="mt-2">
            <MessageBubble role="assistant" content={WELCOME} />
          </div>
        )}

        {!loadingSession && messages.length > visibleCount && (
          <div className="mt-2 text-center">
            <button
              type="button"
              onClick={() => setVisibleCount((v) => v + 100)}
              className="t-cap rounded-full border border-line bg-white px-4 text-primary-deep"
              style={{ minHeight: 48 }}
            >
              加载更早
            </button>
          </div>
        )}

        {timeline.map((item) =>
          item.kind === 'msg' ? (
            <div key={item.msg.key} className="mt-3">
              <MessageBubble
                role={item.msg.role}
                content={item.msg.content}
                streaming={item.msg.streaming}
                error={item.msg.error}
                speaking={speakingKey === item.msg.key}
                onToggleSpeak={
                  item.msg.role === 'assistant' && item.msg.content
                    ? () =>
                        toggleSpeak(
                          item.msg.key,
                          item.msg.presentation?.tts_text || item.msg.content,
                        )
                    : undefined
                }
                onRetry={item.msg.error ? () => retry(item.msg) : undefined}
                actions={item.msg.actions}
                evidence={item.msg.evidence}
                presentation={item.msg.presentation}
              />
            </div>
          ) : (
            <div key={`alert-${item.alert.id}`} className="mt-3">
              <AlertBubble
                alert={item.alert}
                onAck={() => void markRead(item.alert.id)}
                onSpeak={() => toggleSpeak(`alert-${item.alert.id}`, `${item.alert.title}。${item.alert.message}`)}
                onOpen={() => navigate('/me/alerts')}
                speaking={speakingKey === `alert-${item.alert.id}`}
              />
            </div>
          ),
        )}

        {sending && (
          <div className="mt-3 flex justify-start">
            <div className="rounded-btn bg-white px-4 py-3 shadow-card">
              <span className="t-body text-ink-soft">小护士正在思考…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 快捷句 + 输入区 */}
      <div className="shrink-0 px-5 pb-3">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {QUICK_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => sendMessage(q)}
              className="t-cap shrink-0 whitespace-nowrap rounded-full border border-line bg-white px-4 py-3 text-ink-soft"
            >
              {q}
            </button>
          ))}
        </div>

        {/* 语音球上沿锚点（规格 §4.4） */}
        <div id="orb-upper-bound" />

        <div className="flex items-end gap-2 pt-1">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                sendMessage(input)
              }
            }}
            rows={1}
            placeholder="输入您想说的话…"
            aria-label="输入消息"
            className="t-body max-h-32 min-h-[56px] flex-1 resize-none overflow-y-auto rounded-btn border border-line bg-white px-4 py-3"
          />
          <button
            type="button"
            onClick={() => sendMessage(input)}
            disabled={sending || !input.trim()}
            aria-label="发送"
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-btn bg-primary-deep text-white disabled:opacity-50"
          >
            <SendIcon size={26} />
          </button>
        </div>

        <button
          type="button"
          onPointerDown={(e) => {
            e.preventDefault()
            void handleVoiceDown()
          }}
          onPointerUp={(e) => {
            e.preventDefault()
            void handleVoiceUp()
          }}
          onPointerCancel={() => {
            void handleVoiceUp()
          }}
          disabled={sending}
          aria-label="按住说话"
          className={`t-body mt-2 flex w-full items-center justify-center gap-2 rounded-btn font-semibold text-white disabled:opacity-50 ${
            recorder.recording ? 'bg-level-red' : recorder.recognizing ? 'bg-level-orange' : 'bg-primary-deep'
          }`}
          style={{ minHeight: 64, touchAction: 'none' }}
        >
          <MicIcon size={22} />
          {recorder.recording ? '正在聆听… 松手结束' : recorder.recognizing ? '正在识别…' : '按住说话'}
        </button>
      </div>
    </div>
  )
}
