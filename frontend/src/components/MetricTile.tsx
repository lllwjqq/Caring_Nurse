interface MetricTileProps {
  label: string
  value: string
  unit: string
  abnormal?: boolean
  time?: string
  expanded?: boolean
  onClick?: () => void
}

/** 今日指标卡（规格 §6.2）。 */
export default function MetricTile({ label, value, unit, abnormal, time, expanded, onClick }: MetricTileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={expanded}
      className={`w-full rounded-card bg-white p-4 text-left shadow-card ${onClick ? '' : 'cursor-default'}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="t-cap text-ink-soft">{label}</span>
        {abnormal && (
          <span className="t-cap rounded-full bg-level-red px-2 py-0.5 text-white">异常</span>
        )}
      </div>
      <p className="t-display mt-1 leading-none">
        {value}
        <span className="t-cap ml-1 text-ink-soft">{unit}</span>
      </p>
      <p className="t-cap mt-1 text-ink-soft">{time ?? '今日未记录'}</p>
    </button>
  )
}
