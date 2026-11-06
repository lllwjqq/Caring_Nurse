import type { CheckEntry } from '../lib/checkin'
import type { ReminderItem } from '../lib/types'
import { CheckCircleIcon, CheckIcon, XIcon } from './icons'

interface CheckinRowProps {
  reminder: ReminderItem
  slot: string
  entry?: CheckEntry
  onCheck: (status: 'taken' | 'skipped') => void
  onUndo: () => void
}

function doseText(r: ReminderItem): string {
  const dose = `${r.dose ?? ''}${r.dose_unit ?? ''}`.trim()
  return dose || '按医嘱'
}

/** 今日服药打卡行（规格 §6.4.1）。 */
export default function CheckinRow({ reminder, slot, entry, onCheck, onUndo }: CheckinRowProps) {
  return (
    <div className="rounded-card bg-white p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="t-h2 leading-tight">
            {slot} · {reminder.medication_name}
          </p>
          <p className="t-cap mt-1 text-ink-soft">
            {doseText(reminder)}
            {reminder.timing_note ? ` · ${reminder.timing_note}` : ''}
          </p>
        </div>
      </div>

      {entry?.status === 'taken' ? (
        <div className="mt-2 flex items-center gap-2 text-level-green">
          <CheckCircleIcon size={22} />
          <span className="t-body">已服{entry.time ? ` ${entry.time}` : ''}</span>
        </div>
      ) : entry?.status === 'skipped' ? (
        <div className="mt-2 flex items-center justify-between">
          <span className="t-cap text-ink-soft">已跳过</span>
          <button type="button" onClick={onUndo} className="t-cap text-primary-deep underline">
            撤销
          </button>
        </div>
      ) : (
        <div className="mt-3 flex gap-3">
          <button
            type="button"
            onClick={() => onCheck('taken')}
            className="btn btn-primary flex-1"
            style={{ minHeight: 48 }}
          >
            <CheckIcon size={20} /> 已服
          </button>
          <button
            type="button"
            onClick={() => onCheck('skipped')}
            className="btn btn-ghost flex-1"
            style={{ minHeight: 48 }}
          >
            <XIcon size={20} /> 跳过
          </button>
        </div>
      )}
    </div>
  )
}
