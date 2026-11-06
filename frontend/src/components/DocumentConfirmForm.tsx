import { useState } from 'react'
import { featureApi } from '../api/client'
import { useToast } from './Toast'
import { XIcon } from './icons'
import {
  DOC_TYPE_LABELS,
  type MedicalDocumentItem,
  type ParsedMedication,
  type ParsedMetric,
} from '../lib/types'

const GLUCOSE_CONTEXTS = [
  { value: 'fasting', label: '空腹' },
  { value: 'postprandial', label: '餐后2h' },
  { value: 'random', label: '随机' },
  { value: 'bedtime', label: '睡前' },
]

const LIPID_CONTEXTS = [
  { value: 'ldl', label: '低密度脂蛋白' },
  { value: 'tc', label: '总胆固醇' },
  { value: 'tg', label: '甘油三酯' },
  { value: 'hdl', label: '高密度脂蛋白' },
]

const FREQUENCIES = [
  { value: 'qd', label: '每日1次' },
  { value: 'bid', label: '每日2次' },
  { value: 'tid', label: '每日3次' },
  { value: 'qid', label: '每日4次' },
  { value: 'q8h', label: '每8小时' },
  { value: 'qn', label: '睡前' },
  { value: 'prn', label: '按需' },
]

interface DocumentConfirmFormProps {
  document: MedicalDocumentItem
  onConfirmed: (actions: Array<{ type: string; summary: string }>) => void
  onRejected?: () => void
}

function isLowConfidence(confidence?: number | null) {
  return confidence != null && confidence < 0.8
}

/** OCR 识别结果确认表单（规格 §6.3 / §7.6）。 */
export default function DocumentConfirmForm({ document, onConfirmed, onRejected }: DocumentConfirmFormProps) {
  const { showToast } = useToast()
  const parsed = document.parsed_data
  const isPrescription = document.doc_type === 'prescription'
  const supported = isPrescription || document.doc_type === 'lab_report'

  const [metrics, setMetrics] = useState<ParsedMetric[]>(parsed?.metrics ?? [])
  const [medications, setMedications] = useState<ParsedMedication[]>(parsed?.medications ?? [])
  const [examDate, setExamDate] = useState(parsed?.exam_date ?? '')
  const [busy, setBusy] = useState(false)

  const updateMetric = (index: number, patch: Partial<ParsedMetric>) => {
    setMetrics((prev) => prev.map((m, i) => (i === index ? { ...m, ...patch } : m)))
  }
  const removeMetric = (index: number) => {
    setMetrics((prev) => prev.filter((_, i) => i !== index))
  }
  const updateMedication = (index: number, patch: Partial<ParsedMedication>) => {
    setMedications((prev) => prev.map((m, i) => (i === index ? { ...m, ...patch } : m)))
  }
  const removeMedication = (index: number) => {
    setMedications((prev) => prev.filter((_, i) => i !== index))
  }

  const contextOptions = (recordType: string) => {
    if (recordType === 'blood_glucose') return GLUCOSE_CONTEXTS
    if (recordType === 'blood_lipid') return LIPID_CONTEXTS
    return null
  }

  const empty = supported ? (isPrescription ? medications.length === 0 : metrics.length === 0) : false

  const handleConfirm = async () => {
    if (empty) return
    setBusy(true)
    try {
      const payload = isPrescription
        ? { medications }
        : { metrics, exam_date: examDate || undefined }
      const { data } = await featureApi.confirmDocument(document.id, payload)
      onConfirmed((data.actions || []) as Array<{ type: string; summary: string }>)
    } catch {
      showToast('确认失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    setBusy(true)
    try {
      await featureApi.rejectDocument(document.id)
      showToast('已放弃该文档')
      onRejected?.()
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  if (!supported) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="t-cap rounded-full bg-primary/10 px-3 py-1 text-primary-deep">
            {DOC_TYPE_LABELS[document.doc_type] ?? document.doc_type}
          </span>
        </div>
        {/* SPEC-GAP：规格只覆盖化验单/处方，其他类型仅保存识别原文 */}
        <div className="rounded-card border-l-4 border-primary bg-primary/10 p-4">
          <p className="t-body text-primary-deep">
            该文档类型暂不支持自动归档，确认后仅保存识别原文。
          </p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => void handleReject()}
            disabled={busy}
            className="btn btn-ghost flex-1"
            style={{ minHeight: 56 }}
          >
            放弃
          </button>
          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={busy}
            className="btn btn-primary flex-[2]"
            style={{ minHeight: 56 }}
          >
            {busy ? '处理中…' : '保留原文'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="t-cap rounded-full bg-primary/10 px-3 py-1 text-primary-deep">
          {DOC_TYPE_LABELS[document.doc_type] ?? document.doc_type}
        </span>
      </div>

      {isPrescription ? (
        <div className="space-y-3">
          {medications.length === 0 ? (
            <p className="t-body py-4 text-center text-ink-soft">未识别到药品信息，请重拍或放弃</p>
          ) : (
            medications.map((m, i) => (
              <div
                key={i}
                className={`rounded-btn border p-4 ${
                  isLowConfidence(m.confidence)
                    ? 'border-warn bg-level-yellow/30'
                    : 'border-line bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="t-body">{m.generic_name || m.name}</span>
                  <button
                    type="button"
                    onClick={() => removeMedication(i)}
                    aria-label={`移除 ${m.name}`}
                    className="flex h-12 w-12 items-center justify-center rounded-full text-ink-soft"
                  >
                    <XIcon size={20} />
                  </button>
                </div>
                {isLowConfidence(m.confidence) && (
                  <p className="t-cap mt-1 text-level-yellow-ink">注意：识别置信度较低，请核对</p>
                )}

                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="t-cap text-ink-soft">单次剂量</label>
                    <input
                      type="number"
                      step="0.1"
                      value={m.dose ?? ''}
                      onChange={(e) =>
                        updateMedication(i, { dose: e.target.value === '' ? null : Number(e.target.value) })
                      }
                      className="t-body mt-1 w-full rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                    />
                  </div>
                  <div>
                    <label className="t-cap text-ink-soft">单位</label>
                    <input
                      value={m.dose_unit ?? ''}
                      onChange={(e) => updateMedication(i, { dose_unit: e.target.value })}
                      placeholder="片 / mg"
                      className="t-body mt-1 w-full rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                    />
                  </div>
                </div>

                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="t-cap text-ink-soft">频次</label>
                    <select
                      value={m.frequency ?? 'qd'}
                      onChange={(e) => updateMedication(i, { frequency: e.target.value })}
                      className="t-body mt-1 w-full rounded-btn border border-line bg-white px-3 py-2"
                      style={{ minHeight: 48 }}
                    >
                      {FREQUENCIES.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="t-cap text-ink-soft">时点</label>
                    <input
                      value={m.timing_note ?? ''}
                      onChange={(e) => updateMedication(i, { timing_note: e.target.value })}
                      placeholder="饭前 / 饭后 / 睡前"
                      className="t-body mt-1 w-full rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                    />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="t-cap text-ink-soft" htmlFor="exam-date">
              检测日期
            </label>
            <input
              id="exam-date"
              type="date"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
            />
          </div>

          {metrics.length === 0 ? (
            <p className="t-body py-4 text-center text-ink-soft">未识别到指标，请重拍或放弃</p>
          ) : (
            metrics.map((m, i) => (
              <div
                key={i}
                className={`rounded-btn border p-4 ${
                  isLowConfidence(m.confidence)
                    ? 'border-warn bg-level-yellow/30'
                    : 'border-line bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="t-body">{m.name}</span>
                  <button
                    type="button"
                    onClick={() => removeMetric(i)}
                    aria-label={`移除 ${m.name}`}
                    className="flex h-12 w-12 items-center justify-center rounded-full text-ink-soft"
                  >
                    <XIcon size={20} />
                  </button>
                </div>
                {isLowConfidence(m.confidence) && (
                  <p className="t-cap mt-1 text-level-yellow-ink">注意：识别置信度较低，请核对</p>
                )}

                {m.record_type === 'blood_pressure' ? (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <input
                      type="number"
                      value={m.systolic ?? ''}
                      onChange={(e) => {
                        const v = e.target.value === '' ? null : Number(e.target.value)
                        updateMetric(i, { systolic: v, value: v })
                      }}
                      placeholder="收缩压"
                      className="t-body rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                    />
                    <input
                      type="number"
                      value={m.diastolic ?? ''}
                      onChange={(e) =>
                        updateMetric(i, {
                          diastolic: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                      placeholder="舒张压"
                      className="t-body rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                    />
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-2">
                    <input
                      type="number"
                      step="0.1"
                      value={m.value ?? ''}
                      onChange={(e) =>
                        updateMetric(i, { value: e.target.value === '' ? null : Number(e.target.value) })
                      }
                      className="t-body flex-1 rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                    />
                    <input
                      value={m.unit}
                      onChange={(e) => updateMetric(i, { unit: e.target.value })}
                      className="t-body w-28 rounded-btn border border-line px-3 py-2"
                      style={{ minHeight: 48 }}
                      aria-label="单位"
                    />
                  </div>
                )}

                {contextOptions(m.record_type) && (
                  <select
                    value={m.context ?? ''}
                    onChange={(e) => updateMetric(i, { context: e.target.value })}
                    className="t-body mt-2 w-full rounded-btn border border-line bg-white px-3 py-2"
                    style={{ minHeight: 48 }}
                    aria-label="测量场景"
                  >
                    <option value="">未指定场景</option>
                    {contextOptions(m.record_type)!.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            ))
          )}
        </div>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => void handleReject()}
          disabled={busy}
          className="btn btn-ghost flex-1"
          style={{ minHeight: 56 }}
        >
          放弃
        </button>
        <button
          type="button"
          onClick={() => void handleConfirm()}
          disabled={busy || empty}
          className="btn btn-primary flex-[2]"
          style={{ minHeight: 56 }}
        >
          {busy ? '处理中…' : '确认入库'}
        </button>
      </div>
    </div>
  )
}
