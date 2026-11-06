interface SwitchRowProps {
  label: string
  desc?: string
  checked: boolean
  onChange: (checked: boolean) => void
}

/** 设置行 + 开关（规格 §5 / §6.5.4）。 */
export default function SwitchRow({ label, desc, checked, onChange }: SwitchRowProps) {
  return (
    <div className="flex min-h-[64px] items-center justify-between gap-3 border-b border-line py-2 last:border-0">
      <div className="min-w-0">
        <p className="t-body">{label}</p>
        {desc && <p className="t-cap text-ink-soft">{desc}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={`relative h-12 w-20 shrink-0 rounded-full ${checked ? 'bg-primary-deep' : 'bg-line'}`}
      >
        <span
          className={`absolute top-1 h-10 w-10 rounded-full bg-white shadow-card transition-transform ${
            checked ? 'translate-x-9' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  )
}
