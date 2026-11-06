import { useState } from 'react'
import type { AlertItem } from '../lib/types'
import { formatDateTime } from '../constants/healthRecords'

interface AlertListItemProps {
  alert: AlertItem
  onOpen?: () => void
  onResolve?: () => void
}

interface LevelMeta {
  label: string
  bar: string
  pill: string
}

const LEVEL_META: Record<string, LevelMeta> = {
  red: { label: '严重', bar: 'border-l-level-red', pill: 'bg-level-red text-white' },
  orange: { label: '警告', bar: 'border-l-level-orange', pill: 'bg-level-orange text-white' },
  yellow: { label: '关注', bar: 'border-l-warn', pill: 'bg-level-yellow text-level-yellow-ink' },
  green: { label: '提示', bar: 'border-l-level-green', pill: 'bg-level-green text-white' },
}

/** 预警列表项（规格 §6.2）：点击展开详情 + 已处理。 */
export default function AlertListItem({ alert, onOpen, onResolve }: AlertListItemProps) {
  const [expanded, setExpanded] = useState(false)
  const meta = LEVEL_META[alert.level] ?? LEVEL_META.yellow

  return (
    <div className={`overflow-hidden rounded-btn border-l-4 bg-white shadow-card ${meta.bar}`}>
      <button
        type="button"
        onClick={() => {
          setExpanded((v) => !v)
          onOpen?.()
        }}
        aria-expanded={expanded}
        className="w-full p-4 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          <span className="t-h2">{alert.title}</span>
          <span className="t-cap shrink-0 text-ink-soft">{formatDateTime(alert.created_at)}</span>
        </div>
        <p className="t-body mt-1 text-ink-soft">{alert.message}</p>
        <div className="mt-2 flex items-center gap-2">
          <span className={`t-cap rounded-full px-2 py-0.5 ${meta.pill}`}>
            {alert.level_label || meta.label}
          </span>
          <span className="t-cap text-ink-soft">来源：{alert.source_label || '系统'}</span>
          <span className="t-cap text-ink-soft">
            {alert.is_resolved ? '已处理' : alert.is_read ? '已读' : '未读'}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-line px-4 pb-4 pt-3">
          <p className="t-cap text-ink-soft">处理建议</p>
          <p className="t-body mt-1">{alert.suggestion || '请结合医生意见处理，并继续监测。'}</p>
          {!alert.is_resolved && onResolve && (
            <button
              type="button"
              onClick={onResolve}
              className="btn btn-primary mt-3"
              style={{ minHeight: 48 }}
            >
              标记已处理
            </button>
          )}
        </div>
      )}
    </div>
  )
}
