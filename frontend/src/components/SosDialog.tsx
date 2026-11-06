import { useEffect, useRef, useState } from 'react'
import { PhoneIcon, XIcon } from './icons'
import { useToast } from './Toast'

const COUNTDOWN_START = 5
const RING_R = 28
const RING_C = 2 * Math.PI * RING_R

/** 从 emergency_contact 取最后连续 11 位数字（规格 §4.5）。 */
export function extractPhone(contact: string | null | undefined): string | null {
  if (!contact) return null
  const digits = contact.replace(/\D/g, '')
  if (digits.length < 11) return null
  return digits.slice(-11)
}

interface SosDialogProps {
  open: boolean
  contact: string | null | undefined
  onClose: () => void
  onGoSetup: () => void
}

/** SOS 全屏弹窗 + 5 秒倒计时（规格 §4.5 / §7.3）。 */
export default function SosDialog({ open, contact, onClose, onGoSetup }: SosDialogProps) {
  const phone = extractPhone(contact)
  const { showToast } = useToast()
  const [seconds, setSeconds] = useState(COUNTDOWN_START)
  const firedRef = useRef(false)

  useEffect(() => {
    if (!open) return
    firedRef.current = false
    setSeconds(COUNTDOWN_START)
    const timer = window.setInterval(() => {
      setSeconds((prev) => {
        if (prev <= 1) {
          window.clearInterval(timer)
          if (phone && !firedRef.current) {
            firedRef.current = true
            window.location.href = `tel:${phone}`
          }
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [open, phone])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const progress = seconds / COUNTDOWN_START

  const handleCall = () => {
    if (phone) window.location.href = `tel:${phone}`
  }

  const handleCopy = async () => {
    if (!phone) return
    try {
      await navigator.clipboard.writeText(phone)
      showToast('号码已复制')
    } catch {
      showToast('复制失败，请长按号码手动复制')
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center px-4" role="presentation">
      <div
        className="absolute inset-0 animate-fade-in bg-ink/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sos-title"
        className="relative w-full rounded-card bg-white p-6 shadow-card-lg"
        style={{ maxWidth: 'min(86vw, 360px)' }}
      >
        <h2 id="sos-title" className="t-h2 text-center">
          需要紧急帮助吗？
        </h2>

        {phone ? (
          <>
            <p className="t-body mt-3 text-center text-ink-soft">将为您拨打紧急联系人</p>
            <a
              href={`tel:${phone}`}
              className="t-h2 mt-2 block text-center tracking-wide text-primary-deep"
            >
              {phone}
            </a>

            <div className="relative mx-auto mt-3 h-16 w-16" aria-hidden="true">
              <svg width={64} height={64} style={{ transform: 'rotate(-90deg)' }}>
                <circle cx={32} cy={32} r={RING_R} fill="none" stroke="rgb(var(--c-line))" strokeWidth={6} />
                <circle
                  cx={32}
                  cy={32}
                  r={RING_R}
                  fill="none"
                  stroke="rgb(var(--c-level-red))"
                  strokeWidth={6}
                  strokeLinecap="round"
                  strokeDasharray={RING_C}
                  strokeDashoffset={RING_C * (1 - progress)}
                />
              </svg>
              <span className="t-display absolute inset-0 flex items-center justify-center">
                {seconds}
              </span>
            </div>
            <p className="t-cap mt-1 text-center text-ink-soft" aria-live="polite">
              {seconds > 0 ? `${seconds} 秒后自动拨打` : '正在拨打…'}
            </p>

            <div className="mt-5 flex gap-3">
              <button type="button" onClick={onClose} className="btn btn-primary flex-[2]" style={{ minHeight: 56 }}>
                取消
              </button>
              <button type="button" onClick={handleCall} className="btn btn-danger flex-1" style={{ minHeight: 56 }}>
                立即拨打
              </button>
            </div>

            <button
              type="button"
              onClick={handleCopy}
              className="t-cap mt-3 w-full text-center text-primary-deep underline"
            >
              复制号码
            </button>
          </>
        ) : (
          <>
            <p className="t-body mt-3 text-center text-ink-soft">还没有紧急联系人</p>
            <div className="mt-5 flex flex-col gap-3">
              <a
                href="tel:120"
                className="btn btn-danger w-full"
                style={{ minHeight: 56 }}
              >
                <PhoneIcon size={20} /> 拨打 120
              </a>
              <button
                type="button"
                onClick={() => {
                  onClose()
                  onGoSetup()
                }}
                className="btn btn-ghost w-full"
                style={{ minHeight: 56 }}
              >
                去设置添加
              </button>
            </div>
          </>
        )}

        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="absolute right-2 top-2 flex h-12 w-12 items-center justify-center rounded-full text-ink-soft"
        >
          <XIcon size={22} />
        </button>
      </div>
    </div>
  )
}
