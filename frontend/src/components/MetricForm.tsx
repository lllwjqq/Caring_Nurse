import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { healthApi } from '../api/client'
import { useVoice } from '../context/VoiceContext'
import { useToast } from './Toast'
import { PlayIcon } from './icons'
import {
  GLUCOSE_CONTEXTS,
  RECORD_TYPES,
  getReferenceRange,
  toLocalDatetimeValue,
  type GlucoseContext,
  type RecordFeedback,
} from '../constants/healthRecords'

const FEEDBACK_STYLE: Record<string, { bg: string; text: string; border: string }> = {
  green: { bg: 'bg-level-green/10', text: 'text-level-green', border: 'border-level-green' },
  yellow: { bg: 'bg-level-yellow', text: 'text-level-yellow-ink', border: 'border-level-yellow' },
  orange: { bg: 'bg-level-orange/10', text: 'text-level-orange', border: 'border-level-orange' },
  red: { bg: 'bg-level-red/10', text: 'text-level-red', border: 'border-level-red' },
}

/** 生理指标录入表单（规格 §6.3）。 */
export default function MetricForm({ onSubmitted }: { onSubmitted?: () => void }) {
  const voice = useVoice()
  const { showToast } = useToast()

  const [recordType, setRecordType] = useState('blood_glucose')
  const [glucoseContext, setGlucoseContext] = useState<GlucoseContext>('fasting')
  const [value, setValue] = useState('')
  const [systolic, setSystolic] = useState('')
  const [diastolic, setDiastolic] = useState('')
  const [note, setNote] = useState('')
  const [recordedAt, setRecordedAt] = useState(toLocalDatetimeValue())
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<RecordFeedback | null>(null)

  const selectedType = RECORD_TYPES.find((t) => t.value === recordType)
  const previewRange =
    recordType === 'blood_glucose'
      ? getReferenceRange('blood_glucose', glucoseContext)
      : getReferenceRange(recordType)

  const reset = () => {
    setValue('')
    setSystolic('')
    setDiastolic('')
    setNote('')
    setRecordedAt(toLocalDatetimeValue())
    setFeedback(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (recordType === 'blood_pressure') {
      if (!systolic || !diastolic) {
        showToast('请填写收缩压和舒张压')
        return
      }
    } else if (!value) {
      showToast('请填写数值')
      return
    }

    setBusy(true)
    setFeedback(null)
    try {
      const extra_data: Record<string, unknown> = {}
      if (recordType === 'blood_pressure') {
        extra_data.systolic = Number(systolic)
        extra_data.diastolic = Number(diastolic)
      }
      if (recordType === 'blood_glucose') extra_data.type = glucoseContext
      if (note.trim()) extra_data.note = note.trim()

      const { data } = await healthApi.createRecord({
        record_type: recordType,
        value: recordType === 'blood_pressure' ? Number(systolic) : Number(value),
        unit: selectedType?.unit ?? '',
        extra_data,
        recorded_at: new Date(recordedAt).toISOString(),
      })
      setFeedback((data as { feedback: RecordFeedback }).feedback)
      onSubmitted?.()
    } catch {
      showToast('录入失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  if (feedback) {
    const style = FEEDBACK_STYLE[feedback.alert_level ?? 'green'] ?? FEEDBACK_STYLE.green
    return (
      <div className={`rounded-card border-l-4 p-5 ${style.bg} ${style.border}`}>
        <p className={`t-body ${style.text}`}>{feedback.message}</p>
        {feedback.reference_range && (
          <p className={`t-cap mt-1 ${style.text}`}>参考范围：{feedback.reference_range}</p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void voice.speak(feedback.message)}
            className="btn btn-ghost"
            style={{ minHeight: 48 }}
          >
            <PlayIcon size={20} /> 听一遍
          </button>
          {feedback.alert_id && (
            <Link to="/monitor" className="t-cap text-primary-deep underline">
              去监测页看看
            </Link>
          )}
          <button type="button" onClick={reset} className="t-cap text-ink-soft underline">
            继续录入
          </button>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="t-cap text-ink-soft">指标类型</label>
        <div className="mt-2 flex flex-wrap gap-2">
          {RECORD_TYPES.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setRecordType(t.value)}
              aria-pressed={recordType === t.value}
              className={`t-body rounded-full border px-4 ${
                recordType === t.value
                  ? 'bg-primary-deep text-white'
                  : 'border-line bg-white text-ink'
              }`}
              style={{ minHeight: 48 }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {recordType === 'blood_glucose' && (
        <div>
          <label className="t-cap text-ink-soft">测量场景</label>
          <div className="mt-2 flex flex-wrap gap-2">
            {GLUCOSE_CONTEXTS.map((c) => (
              <button
                key={c.value}
                type="button"
                onClick={() => setGlucoseContext(c.value)}
                aria-pressed={glucoseContext === c.value}
                className={`t-body rounded-full border px-4 ${
                  glucoseContext === c.value
                    ? 'bg-primary-deep text-white'
                    : 'border-line bg-white text-ink'
                }`}
                style={{ minHeight: 48 }}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {recordType === 'blood_pressure' ? (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="t-cap text-ink-soft" htmlFor="metric-systolic">
              收缩压
            </label>
            <input
              id="metric-systolic"
              type="number"
              inputMode="decimal"
              value={systolic}
              onChange={(e) => setSystolic(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
              required
            />
          </div>
          <div>
            <label className="t-cap text-ink-soft" htmlFor="metric-diastolic">
              舒张压
            </label>
            <input
              id="metric-diastolic"
              type="number"
              inputMode="decimal"
              value={diastolic}
              onChange={(e) => setDiastolic(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
              required
            />
          </div>
        </div>
      ) : (
        <div>
          <label className="t-cap text-ink-soft" htmlFor="metric-value">
            数值（{selectedType?.unit}）
          </label>
          <input
            id="metric-value"
            type="number"
            inputMode="decimal"
            step="0.1"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
            required
          />
        </div>
      )}

      <div>
        <label className="t-cap text-ink-soft" htmlFor="metric-time">
          测量时间
        </label>
        <input
          id="metric-time"
          type="datetime-local"
          value={recordedAt}
          onChange={(e) => setRecordedAt(e.target.value)}
          className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
          style={{ minHeight: 48 }}
          required
        />
      </div>

      <div>
        <label className="t-cap text-ink-soft" htmlFor="metric-note">
          备注（可选）
        </label>
        <input
          id="metric-note"
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="如：早餐吃了包子"
          className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
          style={{ minHeight: 48 }}
        />
      </div>

      {previewRange && (
        <p className="t-cap rounded-btn bg-mist px-3 py-2 text-ink-soft">参考范围：{previewRange}</p>
      )}

      <button type="submit" disabled={busy} className="btn btn-primary w-full" style={{ minHeight: 56 }}>
        {busy ? '提交中…' : '提交记录'}
      </button>
    </form>
  )
}
