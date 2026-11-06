import { PhoneIcon } from './icons'

/** 页头 SOS 红色胶囊（规格 §4.5：88×48）。 */
export default function SosButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="紧急求助"
      className="flex shrink-0 items-center justify-center gap-1 rounded-full px-4 text-white"
      style={{
        minWidth: 88,
        height: 48,
        background: 'rgb(var(--c-level-red))',
      }}
    >
      <PhoneIcon size={20} />
      <span className="t-body leading-none" style={{ fontWeight: 700 }}>
        SOS
      </span>
    </button>
  )
}
