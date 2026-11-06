import type { AgentAction, AgentEvidence, AgentPresentation } from '../lib/types'
import PresentationView from './PresentationView'
import { PlayIcon, StopIcon } from './icons'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  error?: boolean
  speaking?: boolean
  actions?: AgentAction[]
  evidence?: AgentEvidence[]
  presentation?: AgentPresentation
  onToggleSpeak?: () => void
  onRetry?: () => void
}

/** 对话气泡（规格 §6.1 气泡规格 / IO_SPEC §3）。 */
export default function MessageBubble({
  role,
  content,
  streaming,
  error,
  speaking,
  actions,
  evidence,
  presentation,
  onToggleSpeak,
  onRetry,
}: MessageBubbleProps) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-btn bg-primary-deep px-4 py-3 text-white">
          <span className="t-body">{content}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-btn bg-white px-4 py-3 shadow-card">
        {!streaming && !error && presentation?.summary ? (
          <>
            <PresentationView presentation={presentation} />
            {content && (
              <details className="mt-2">
                <summary className="t-cap cursor-pointer text-primary-deep">查看全文</summary>
                <p className="t-body mt-2 whitespace-pre-wrap text-ink">{content}</p>
              </details>
            )}
          </>
        ) : (
          <p className="t-body whitespace-pre-wrap text-ink">
            {content}
            {streaming && <span className="text-ink-soft">…</span>}
          </p>
        )}

        {error && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="t-cap mt-2 rounded-btn border border-line px-4 text-primary-deep"
            style={{ minHeight: 48 }}
          >
            重试
          </button>
        )}

        {evidence && evidence.length > 0 && (
          <div className="mt-2 rounded-btn bg-mist p-2">
            <p className="t-cap text-ink-soft">依据</p>
            {evidence.slice(0, 3).map((item, index) => (
              <p key={index} className="t-cap text-ink-soft">
                · {item.title || item.source || '知识库'}
                {item.title && item.source ? `（${item.source}）` : ''}
              </p>
            ))}
          </div>
        )}

        {actions && actions.length > 0 && (
          <div className="mt-2 space-y-1">
            {actions.slice(0, 3).map((action, index) => (
              <p key={index} className="t-cap text-level-green">
                · {action.summary || action.type}
              </p>
            ))}
          </div>
        )}

        {!streaming && !error && content && onToggleSpeak && (
          <button
            type="button"
            onClick={onToggleSpeak}
            className="t-cap mt-1 flex min-h-[48px] items-center gap-1 text-primary-deep"
          >
            {speaking ? <StopIcon size={20} /> : <PlayIcon size={20} />}
            {speaking ? '停止' : '听一遍'}
          </button>
        )}
      </div>
    </div>
  )
}
