import type { AgentPresentation } from '../lib/types'
import { CheckIcon } from './icons'

interface PresentationViewProps {
  presentation?: AgentPresentation
}

/** 结构化呈现（IO_SPEC §3.1）：结论 + 关键信息 + 用户行动 + 边界。 */
export default function PresentationView({ presentation }: PresentationViewProps) {
  if (!presentation) return null
  const { summary, key_points, action_items, boundary } = presentation
  if (!summary && !key_points?.length && !action_items?.length && !boundary) return null

  return (
    <div className="space-y-3">
      {summary && <p className="t-h2 text-ink">{summary}</p>}

      {key_points && key_points.length > 0 && (
        <ul className="space-y-1">
          {key_points.slice(0, 3).map((point, index) => (
            <li key={index} className="t-body flex items-start gap-2 text-ink">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      )}

      {action_items && action_items.length > 0 && (
        <div className="rounded-btn bg-mist p-3">
          <p className="t-cap text-ink-soft">您现在可以做</p>
          <ul className="mt-1 space-y-1">
            {action_items.slice(0, 2).map((item, index) => (
              <li key={index} className="t-body flex items-start gap-2 text-ink">
                <CheckIcon size={18} />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {boundary && <p className="t-cap text-ink-soft">{boundary}</p>}
    </div>
  )
}
