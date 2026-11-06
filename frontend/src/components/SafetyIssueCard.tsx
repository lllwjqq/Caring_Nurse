interface SafetyIssueLike {
  level: string
  title: string
  why: string
  advice: string
}

const STYLE: Record<string, { bar: string; pill: string }> = {
  red: { bar: 'border-l-level-red', pill: 'bg-level-red text-white' },
  orange: { bar: 'border-l-level-orange', pill: 'bg-level-orange text-white' },
  yellow: { bar: 'border-l-warn', pill: 'bg-level-yellow text-level-yellow-ink' },
}

/** 用药安全提示卡（规格 §6.4 / §6.4.3）。兼容后端与本地兜底两种结构。 */
export default function SafetyIssueCard({ issue }: { issue: SafetyIssueLike }) {
  const style = STYLE[issue.level] ?? STYLE.yellow

  return (
    <div className={`rounded-btn border-l-4 bg-white p-4 shadow-card ${style.bar}`}>
      <div className="flex items-center gap-2">
        <span className={`t-cap rounded-full px-2 py-0.5 ${style.pill}`}>
          {issue.level === 'red' ? '高风险' : issue.level === 'orange' ? '需注意' : '待补充'}
        </span>
        <h3 className="t-h2 min-w-0 flex-1">{issue.title}</h3>
      </div>
      <p className="t-body mt-2 text-ink-soft">{issue.why}</p>
      <p className="t-cap mt-1 text-primary-deep">建议：{issue.advice}</p>
    </div>
  )
}
