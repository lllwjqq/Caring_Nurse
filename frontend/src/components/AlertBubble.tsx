import type { AlertItem } from '../lib/types'
import { AlertTriangleIcon, PlayIcon, StopIcon } from './icons'

interface AlertBubbleProps {
  alert: AlertItem
  onAck: () => void
  onSpeak: () => void
  onOpen: () => void
  speaking: boolean
}

interface LevelMeta {
  label: string
  bar: string
  pill: string
}

const LEVEL_META: Record<string, LevelMeta> = {
  red: { label: '严重异常', bar: 'border-l-level-red', pill: 'bg-level-red text-white' },
  orange: { label: '需要尽快处理', bar: 'border-l-level-orange', pill: 'bg-level-orange text-white' },
  yellow: {
    label: '需要关注',
    bar: 'border-l-warn',
    pill: 'bg-level-yellow text-level-yellow-ink',
  },
  green: { label: '提示', bar: 'border-l-level-green', pill: 'bg-level-green text-white' },
}

/** 问诊内预警气泡（规格 §6.1）。 */
export default function AlertBubble({ alert, onAck, onSpeak, onOpen, speaking }: AlertBubbleProps) {
  const meta = LEVEL_META[alert.level] ?? LEVEL_META.yellow
  const levelText = alert.level_label || meta.label
  const sourceText = alert.source_label || '系统'

  return (
    <div className={`rounded-btn border-l-4 bg-white p-4 shadow-card ${meta.bar}`}>
      <div className="flex items-center gap-2">
        <AlertTriangleIcon size={20} className="text-ink-soft" />
        <span className={`t-cap rounded-full px-2 py-0.5 ${meta.pill}`}>预警 · {levelText}</span>
      </div>

      <h3 className="t-h2 mt-2 text-ink">{alert.title}</h3>
      <p className="t-body mt-1 text-ink-soft">{alert.message}</p>
      <p className="t-cap mt-1 text-ink-soft">来源：{sourceText}</p>
      {alert.suggestion && <p className="t-cap mt-2 text-primary-deep">{alert.suggestion}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" onClick={onAck} className="btn btn-primary" style={{ minHeight: 56 }}>
          已了解
        </button>
        <button type="button" onClick={onSpeak} className="btn btn-ghost" style={{ minHeight: 48 }}>
          {speaking ? <StopIcon size={20} /> : <PlayIcon size={20} />}
          {speaking ? '停止' : '听一遍'}
        </button>
        <button type="button" onClick={onOpen} className="t-cap text-primary-deep underline">
          查看详情
        </button>
      </div>
    </div>
  )
}
