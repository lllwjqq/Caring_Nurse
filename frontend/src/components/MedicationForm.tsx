import { useState, type FormEvent } from 'react'
import { reminderApi } from '../api/client'
import { useToast } from './Toast'
import type { ReminderItem } from '../lib/types'

const FREQUENCIES = [
  { value: 'qd', label: '每日1次' },
  { value: 'bid', label: '每日2次' },
  { value: 'tid', label: '每日3次' },
  { value: 'qid', label: '每日4次' },
  { value: 'q8h', label: '每8小时' },
  { value: 'qn', label: '睡前' },
  { value: 'prn', label: '按需' },
]

interface MedicationFormProps {
  initial?: ReminderItem | null
  onSaved?: () => void
}

/** 药品录入/编辑表单（规格 §6.3 / §6.4.2）。 */
export default function MedicationForm({ initial, onSaved }: MedicationFormProps) {
  const { showToast } = useToast()
  const [name, setName] = useState(initial?.medication_name ?? '')
  const [dose, setDose] = useState(initial?.dose != null ? String(initial.dose) : '')
  const [unit, setUnit] = useState(initial?.dose_unit ?? '')
  const [frequency, setFrequency] = useState(initial?.frequency ?? 'qd')
  const [timing, setTiming] = useState(initial?.timing_note ?? '')
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      showToast('请填写药名')
      return
    }
    setBusy(true)
    try {
      const payload = {
        medication_name: name.trim(),
        dose: dose ? Number(dose) : undefined,
        dose_unit: unit.trim() || undefined,
        frequency,
        timing_note: timing.trim() || undefined,
      }
      if (initial) {
        await reminderApi.update(initial.id, payload)
        showToast('已更新服药提醒')
      } else {
        await reminderApi.create(payload)
        showToast('已添加服药提醒')
        setName('')
        setDose('')
        setUnit('')
        setTiming('')
      }
      onSaved?.()
    } catch {
      showToast('保存失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="t-cap text-ink-soft" htmlFor="med-name">
          药名
        </label>
        <input
          id="med-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="如：阿司匹林肠溶片"
          className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
          style={{ minHeight: 48 }}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="t-cap text-ink-soft" htmlFor="med-dose">
            单次剂量
          </label>
          <input
            id="med-dose"
            type="number"
            step="0.1"
            value={dose}
            onChange={(e) => setDose(e.target.value)}
            placeholder="如：1"
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>
        <div>
          <label className="t-cap text-ink-soft" htmlFor="med-unit">
            单位
          </label>
          <input
            id="med-unit"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder="片 / mg"
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>
      </div>

      <div>
        <span className="t-cap text-ink-soft">频次</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {FREQUENCIES.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFrequency(f.value)}
              aria-pressed={frequency === f.value}
              className={`t-body rounded-full border px-4 ${
                frequency === f.value
                  ? 'bg-primary-deep text-white'
                  : 'border-line bg-white text-ink'
              }`}
              style={{ minHeight: 48 }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="t-cap text-ink-soft" htmlFor="med-timing">
          时点（可选）
        </label>
        <input
          id="med-timing"
          value={timing}
          onChange={(e) => setTiming(e.target.value)}
          placeholder="饭前 / 饭后 / 睡前"
          className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
          style={{ minHeight: 48 }}
        />
      </div>

      <button type="submit" disabled={busy} className="btn btn-primary w-full" style={{ minHeight: 56 }}>
        {busy ? '保存中…' : initial ? '保存修改' : '保存提醒'}
      </button>
    </form>
  )
}
