import { useEffect, useRef, useState } from 'react'
import { healthApi, reminderApi } from '../api/client'
import { useAlert } from '../context/AlertContext'
import { useVoice } from '../context/VoiceContext'
import { useToast } from './Toast'
import { XIcon } from './icons'

/**
 * 语音导入确认卡（规格 §7.1）：先复述、后入库。
 * 全局渲染于 AppShell，草稿来自 VoiceContext（语音球 / 语音面板 / 问诊输入区）。
 */
export default function VoiceConfirmCard() {
  const { draft, clearDraft, speak } = useVoice()
  const { refresh } = useAlert()
  const { showToast } = useToast()
  const [busy, setBusy] = useState(false)
  const lastSpokenRef = useRef<string | null>(null)

  // 语音复述（规格 §7.1 ④）：只对同一草稿复述一次，避免重复渲染重复播报
  useEffect(() => {
    if (!draft) {
      lastSpokenRef.current = null
      return
    }
    if (lastSpokenRef.current === draft.label) return
    lastSpokenRef.current = draft.label
    void speak(`我听到您说，${draft.label}，对吗？`)
  }, [draft, speak])

  if (!draft) return null

  const handleConfirm = async () => {
    setBusy(true)
    try {
      if (draft.kind === 'metric') {
        await healthApi.createRecord({
          record_type: draft.record_type,
          value: draft.value,
          unit: draft.unit,
          extra_data: draft.extra_data,
        })
      } else {
        await reminderApi.create({
          medication_name: draft.medication_name,
          dose: draft.dose,
          dose_unit: draft.dose_unit,
          frequency: draft.frequency ?? 'qd',
        })
      }
      clearDraft()
      showToast('已经帮您记好了')
      void speak('已经帮您记好了')
      void refresh()
    } catch {
      showToast('记录失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[70]" role="presentation">
      <div className="absolute inset-0 animate-fade-in bg-ink/50" onClick={clearDraft} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="voice-confirm-title"
        className="absolute bottom-0 left-1/2 w-full max-w-shell -translate-x-1/2 animate-sheet-in rounded-t-card bg-white px-5 pt-4"
        style={{ paddingBottom: 'calc(20px + var(--safe-bottom))' }}
      >
        <div className="flex items-start justify-between">
          <h2 id="voice-confirm-title" className="t-h1">
            我听到您说
          </h2>
          <button
            type="button"
            onClick={clearDraft}
            aria-label="关闭"
            className="flex h-12 w-12 items-center justify-center rounded-full text-ink-soft"
          >
            <XIcon size={24} />
          </button>
        </div>

        <p className="t-display mt-2 text-primary-deep">{draft.label}</p>
        <p className="t-cap mt-3 text-ink-soft">原始识别：{draft.raw}</p>

        <div className="mt-5 flex gap-3">
          <button
            type="button"
            onClick={handleConfirm}
            disabled={busy}
            className="btn btn-primary flex-[2]"
            style={{ minHeight: 56 }}
          >
            {busy ? '记录中…' : '对，记下来'}
          </button>
          <button
            type="button"
            onClick={clearDraft}
            disabled={busy}
            className="btn btn-ghost flex-1"
            style={{ minHeight: 56 }}
          >
            不对，重说
          </button>
        </div>
      </div>
    </div>
  )
}
