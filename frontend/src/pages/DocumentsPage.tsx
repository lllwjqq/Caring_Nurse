import { useEffect, useState } from 'react'
import { featureApi } from '../api/client'

interface Metric {
  record_type: string
  name: string
  value: number | null
  unit: string
  context?: string | null
  systolic?: number | null
  diastolic?: number | null
  reference?: string | null
  abnormal_flag?: string | null
  confidence?: number
}

interface Medication {
  name: string
  generic_name?: string | null
  brand_name?: string | null
  spec?: string | null
  dose?: number | null
  dose_unit?: string | null
  frequency?: string
  route?: string | null
  timing_note?: string | null
  duration_days?: number | null
  notes?: string | null
  confidence?: number
}

interface ParsedData {
  doc_type: string
  confidence?: number
  exam_date?: string | null
  metrics: Metric[]
  medications?: Medication[]
}

interface Doc {
  id: number
  filename: string
  doc_type: string
  confidence: number | null
  ocr_text: string | null
  parsed_data: ParsedData | null
  status: string
  created_at: string
}

interface Action {
  type: string
  summary: string
  record_id?: number | null
  reminder_id?: number | null
}

const DOC_TYPE_LABELS: Record<string, string> = {
  lab_report: '体检/化验单',
  prescription: '处方/医嘱',
  discharge_summary: '出院小结',
  drug_insert: '药品说明书',
  other: '其他文档',
}

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

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  confirmed: { label: '已确认', cls: 'bg-green-100 text-green-700' },
  discarded: { label: '已放弃', cls: 'bg-gray-100 text-gray-500' },
  awaiting_confirmation: { label: '待确认', cls: 'bg-yellow-100 text-yellow-700' },
  uploaded: { label: '待处理', cls: 'bg-blue-100 text-blue-700' },
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Doc[]>([])
  const [pending, setPending] = useState<Doc | null>(null)
  const [metrics, setMetrics] = useState<Metric[]>([])
  const [medications, setMedications] = useState<Medication[]>([])
  const [examDate, setExamDate] = useState('')
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [actions, setActions] = useState<Action[]>([])

  const load = () => {
    featureApi.listDocuments().then((res) => setDocuments(res.data)).catch(() => {})
  }

  useEffect(() => { load() }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setMessage('')
    setActions([])
    try {
      const { data } = await featureApi.uploadDocument(file)
      setPending(data)
      const parsed = data.parsed_data as ParsedData | null
      if (data.doc_type === 'prescription') {
        setMedications(parsed?.medications ?? [])
        setMetrics([])
      } else {
        setMetrics(parsed?.metrics ?? [])
        setMedications([])
      }
      setExamDate(parsed?.exam_date ?? '')
      load()
    } catch {
      setMessage('上传失败，请重试')
    } finally {
      setUploading(false)
    }
  }

  const updateMetric = (i: number, patch: Partial<Metric>) => {
    setMetrics((prev) => prev.map((m, idx) => (idx === i ? { ...m, ...patch } : m)))
  }

  const removeMetric = (i: number) => {
    setMetrics((prev) => prev.filter((_, idx) => idx !== i))
  }

  const updateMedication = (i: number, patch: Partial<Medication>) => {
    setMedications((prev) => prev.map((m, idx) => (idx === i ? { ...m, ...patch } : m)))
  }

  const removeMedication = (i: number) => {
    setMedications((prev) => prev.filter((_, idx) => idx !== i))
  }

  const handleConfirm = async () => {
    if (!pending) return
    setBusy(true)
    setMessage('')
    try {
      const isPrescription = pending.doc_type === 'prescription'
      const payload = isPrescription
        ? { medications }
        : { metrics, exam_date: examDate || undefined }
      const { data } = await featureApi.confirmDocument(pending.id, payload)
      setActions(data.actions)
      setPending(null)
      setMessage('已确认并归档')
      load()
    } catch {
      setMessage('确认失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    if (!pending) return
    setBusy(true)
    try {
      await featureApi.rejectDocument(pending.id)
      setPending(null)
      setMessage('已放弃该文档')
      load()
    } catch {
      setMessage('操作失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const contextOptions = (recordType: string) => {
    if (recordType === 'blood_glucose') return GLUCOSE_CONTEXTS
    if (recordType === 'blood_lipid') return LIPID_CONTEXTS
    return null
  }

  const isLowConfidence = (c?: number | null) => c != null && c < 0.8
  const isPrescription = pending?.doc_type === 'prescription'

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <h3 className="font-semibold mb-2">上传医疗单据</h3>
        <p className="text-sm text-gray-500 mb-4">支持拍照或上传图片/PDF，系统自动 OCR 识别并抽取健康指标/用药信息</p>
        <label className="block w-full border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-primary">
          <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={handleUpload} className="hidden" />
          <div className="text-3xl mb-2">📤</div>
          <p className="text-sm text-gray-500">{uploading ? '识别中...' : '点击拍照或选择文件'}</p>
        </label>
        {message && <p className="text-sm text-primary mt-2">{message}</p>}
      </div>

      {actions.length > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-2xl p-4">
          <h4 className="font-medium text-green-800 mb-2">已执行的操作</h4>
          <ul className="space-y-1">
            {actions.map((a, i) => (
              <li key={i} className="text-sm text-green-700">✓ {a.summary}</li>
            ))}
          </ul>
        </div>
      )}

      {pending && (
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-primary/20">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold">确认识别结果</h3>
            <span className="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded-full">
              {DOC_TYPE_LABELS[pending.doc_type] || pending.doc_type}
            </span>
          </div>

          {isPrescription ? (
            <div className="space-y-3">
              {medications.length === 0 ? (
                <p className="text-sm text-gray-500 py-4 text-center">未识别到药品信息，请检查图片清晰度后重试</p>
              ) : (
                medications.map((m, i) => (
                  <div
                    key={i}
                    className={`rounded-lg p-3 border ${isLowConfidence(m.confidence) ? 'bg-yellow-50 border-yellow-200' : 'bg-gray-50 border-transparent'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{m.generic_name || m.name}</span>
                      <button
                        type="button"
                        onClick={() => removeMedication(i)}
                        className="text-xs text-gray-400 hover:text-red-500"
                      >
                        移除
                      </button>
                    </div>
                    {isLowConfidence(m.confidence) && (
                      <p className="text-xs text-yellow-600 mt-0.5">⚠ 识别置信度较低，请核对</p>
                    )}
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <div>
                        <label className="text-xs text-gray-500">单次剂量</label>
                        <input
                          type="number"
                          step="0.1"
                          value={m.dose ?? ''}
                          onChange={(e) => updateMedication(i, { dose: e.target.value === '' ? null : Number(e.target.value) })}
                          className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">单位</label>
                        <input
                          value={m.dose_unit ?? ''}
                          onChange={(e) => updateMedication(i, { dose_unit: e.target.value })}
                          placeholder="片 / mg"
                          className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <div>
                        <label className="text-xs text-gray-500">频次</label>
                        <select
                          value={m.frequency ?? 'qd'}
                          onChange={(e) => updateMedication(i, { frequency: e.target.value })}
                          className="w-full mt-1 px-3 py-2 border rounded-lg text-sm bg-white"
                        >
                          {FREQUENCIES.map((f) => (
                            <option key={f.value} value={f.value}>{f.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">时点</label>
                        <input
                          value={m.timing_note ?? ''}
                          onChange={(e) => updateMedication(i, { timing_note: e.target.value })}
                          placeholder="饭前 / 饭后 / 睡前"
                          className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                        />
                      </div>
                    </div>
                    {m.notes && (
                      <p className="text-xs text-gray-500 mt-2">备注：{m.notes}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {metrics.length === 0 ? (
                <p className="text-sm text-gray-500 py-4 text-center">未识别到可归档的指标，请检查图片清晰度后重试</p>
              ) : (
                <>
                  <div>
                    <label className="text-xs text-gray-500">检测日期</label>
                    <input
                      type="date"
                      value={examDate}
                      onChange={(e) => setExamDate(e.target.value)}
                      className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                    />
                  </div>

                  {metrics.map((m, i) => (
                    <div
                      key={i}
                      className={`rounded-lg p-3 border ${isLowConfidence(m.confidence) ? 'bg-yellow-50 border-yellow-200' : 'bg-gray-50 border-transparent'}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{m.name}</span>
                        <button
                          type="button"
                          onClick={() => removeMetric(i)}
                          className="text-xs text-gray-400 hover:text-red-500"
                        >
                          移除
                        </button>
                      </div>

                      {isLowConfidence(m.confidence) && (
                        <p className="text-xs text-yellow-600 mt-0.5">⚠ 识别置信度较低，请核对</p>
                      )}

                      {m.record_type === 'blood_pressure' ? (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          <input
                            type="number"
                            value={m.systolic ?? ''}
                            onChange={(e) => updateMetric(i, { systolic: e.target.value === '' ? null : Number(e.target.value), value: e.target.value === '' ? null : Number(e.target.value) })}
                            placeholder="收缩压"
                            className="px-3 py-2 border rounded-lg text-sm"
                          />
                          <input
                            type="number"
                            value={m.diastolic ?? ''}
                            onChange={(e) => updateMetric(i, { diastolic: e.target.value === '' ? null : Number(e.target.value) })}
                            placeholder="舒张压"
                            className="px-3 py-2 border rounded-lg text-sm"
                          />
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 mt-2">
                          <input
                            type="number"
                            step="0.1"
                            value={m.value ?? ''}
                            onChange={(e) => updateMetric(i, { value: e.target.value === '' ? null : Number(e.target.value) })}
                            className="flex-1 px-3 py-2 border rounded-lg text-sm"
                          />
                          <span className="text-xs text-gray-500 whitespace-nowrap">{m.unit}</span>
                        </div>
                      )}

                      {contextOptions(m.record_type) && (
                        <select
                          value={m.context ?? ''}
                          onChange={(e) => updateMetric(i, { context: e.target.value })}
                          className="w-full mt-2 px-3 py-2 border rounded-lg text-sm bg-white"
                        >
                          {contextOptions(m.record_type)!.map((c) => (
                            <option key={c.value} value={c.value}>{c.label}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <button
              type="button"
              onClick={handleReject}
              disabled={busy}
              className="flex-1 py-3 rounded-xl border border-gray-200 text-gray-600 font-medium disabled:opacity-50"
            >
              放弃
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={busy || (isPrescription ? medications.length === 0 : metrics.length === 0)}
              className="flex-1 bg-primary text-white py-3 rounded-xl font-medium disabled:opacity-50"
            >
              {busy ? '处理中...' : '确认入库'}
            </button>
          </div>
        </div>
      )}

      {documents.length > 0 && (
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <h3 className="font-semibold mb-3">历史单据</h3>
          <div className="space-y-3">
            {documents.map((doc) => {
              const status = STATUS_LABELS[doc.status] || { label: doc.status, cls: 'bg-gray-100 text-gray-500' }
              const parsed = doc.parsed_data
              return (
                <div key={doc.id} className="py-3 border-b border-gray-50 last:border-0">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium truncate">{doc.filename}</h4>
                    <span className={`text-xs px-2 py-1 rounded-full ${status.cls}`}>{status.label}</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                  </p>
                  {parsed?.metrics && parsed.metrics.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {parsed.metrics.map((m, i) => (
                        <span key={i} className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">
                          {m.name} {m.record_type === 'blood_pressure' ? `${m.systolic}/${m.diastolic}` : m.value}
                          {m.unit}
                        </span>
                      ))}
                    </div>
                  )}
                  {parsed?.medications && parsed.medications.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {parsed.medications.map((m, i) => (
                        <span key={i} className="text-xs bg-purple-50 text-purple-700 px-2 py-1 rounded">
                          {m.generic_name || m.name} {m.dose ?? ''}{m.dose_unit ?? ''}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
