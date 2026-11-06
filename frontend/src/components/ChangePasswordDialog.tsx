import { useEffect, useState } from 'react'
import { authApi } from '../api/client'
import { useToast } from './Toast'
import { XIcon } from './icons'

interface ChangePasswordDialogProps {
  open: boolean
  onClose: () => void
}

/** 修改密码弹窗（规格附录 A.2）。 */
export default function ChangePasswordDialog({ open, onClose }: ChangePasswordDialogProps) {
  const { showToast } = useToast()
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setOldPassword('')
    setNewPassword('')
    setConfirm('')
    setError('')
    setBusy(false)
  }, [open])

  if (!open) return null

  const submit = async () => {
    if (!oldPassword) {
      setError('请输入原密码')
      return
    }
    if (newPassword.length < 6) {
      setError('新密码至少 6 位')
      return
    }
    if (newPassword !== confirm) {
      setError('两次输入的新密码不一致')
      return
    }
    setBusy(true)
    setError('')
    try {
      await authApi.changePassword({ old_password: oldPassword, new_password: newPassword })
      showToast('密码已修改')
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || '修改失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4" role="presentation">
      <div className="absolute inset-0 animate-fade-in bg-ink/50" onClick={onClose} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pwd-title"
        className="relative w-full rounded-card bg-white p-6 shadow-card-lg"
        style={{ maxWidth: 'min(86vw, 360px)' }}
      >
        <h2 id="pwd-title" className="t-h2">
          修改密码
        </h2>

        <div className="mt-4 space-y-3">
          <input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            placeholder="原密码"
            aria-label="原密码"
            className="t-body w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="新密码（至少 6 位）"
            aria-label="新密码"
            className="t-body w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="再次输入新密码"
            aria-label="确认新密码"
            className="t-body w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>

        {error && <p className="t-cap mt-2 text-level-red">{error}</p>}

        <div className="mt-5 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost flex-1"
            style={{ minHeight: 56 }}
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy}
            className="btn btn-primary flex-1"
            style={{ minHeight: 56 }}
          >
            {busy ? '提交中…' : '确认修改'}
          </button>
        </div>

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
