interface BigTextToggleProps {
  value: boolean
  onChange: (value: boolean) => void
}

/** 大字模式开关（规格 §6.5.4）。 */
export default function BigTextToggle({ value, onChange }: BigTextToggleProps) {
  return (
    <div className="flex min-h-[64px] items-center justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="t-body">大字模式</p>
        <p className="t-cap text-ink-soft">放大所有文字，方便阅读</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        aria-label="大字模式"
        onClick={() => onChange(!value)}
        className={`relative h-12 w-20 shrink-0 rounded-full ${value ? 'bg-primary-deep' : 'bg-line'}`}
      >
        <span
          className={`absolute top-1 h-10 w-10 rounded-full bg-white shadow-card transition-transform ${
            value ? 'translate-x-9' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  )
}
