import { XIcon } from './icons'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message?: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** 自定义二次确认弹窗（规格 §10：禁止 window.confirm，取消键更大）。 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确认',
  danger,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center px-4" role="presentation">
      <div className="absolute inset-0 animate-fade-in bg-ink/50" onClick={onCancel} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="relative w-full rounded-card bg-white p-6 shadow-card-lg"
        style={{ maxWidth: 'min(86vw, 360px)' }}
      >
        <h2 id="confirm-title" className="t-h2">
          {title}
        </h2>
        {message && <p className="t-body mt-2 text-ink-soft">{message}</p>}

        <div className="mt-5 flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="btn btn-primary flex-[2]"
            style={{ minHeight: 56 }}
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`btn flex-1 ${danger ? 'btn-danger' : 'btn-primary'}`}
            style={{ minHeight: 56 }}
          >
            {confirmLabel}
          </button>
        </div>

        <button
          type="button"
          onClick={onCancel}
          aria-label="关闭"
          className="absolute right-2 top-2 flex h-12 w-12 items-center justify-center rounded-full text-ink-soft"
        >
          <XIcon size={22} />
        </button>
      </div>
    </div>
  )
}
