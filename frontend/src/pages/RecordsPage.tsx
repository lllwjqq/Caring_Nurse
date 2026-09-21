import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { healthApi } from '../api/client'
import {
  FEEDBACK_STYLES,
  GLUCOSE_CONTEXTS,
  type GlucoseContext,
  type HealthRecordCreateResult,
  type HealthRecordItem,
  type RecordFeedback,
  RECORD_TYPES,
  formatDateTime,
  formatRecordLabel,
  formatRecordValue,
  getReferenceRange,
  toLocalDatetimeValue,
} from '../constants/healthRecords'

const LIFESTYLE_TYPES = [
  { value: 'diet', label: '饮食' },
  { value: 'exercise', label: '运动' },
  { value: 'sleep', label: '作息' },
]

export default function RecordsPage() {
  const [tab, setTab] = useState<'vital' | 'lifestyle'>('vital')
  const [recordType, setRecordType] = useState('blood_glucose')
  const [glucoseContext, setGlucoseContext] = useState<GlucoseContext>('fasting')
  const [value, setValue] = useState('')
  const [systolic, setSystolic] = useState('')
  const [diastolic, setDiastolic] = useState('')
  const [note, setNote] = useState('')
  const [recordedAt, setRecordedAt] = useState(toLocalDatetimeValue())
  const [lifestyleType, setLifestyleType] = useState('diet')
  const [content, setContent] = useState('')
  const [message, setMessage] = useState('')
  const [feedback, setFeedback] = useState<RecordFeedback | null>(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<HealthRecordItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const selectedType = RECORD_TYPES.find((t) => t.value === recordType)
  const previewRange =
    recordType === 'blood_glucose'
      ? getReferenceRange('blood_glucose', glucoseContext)
      : getReferenceRange(recordType)

  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    healthApi
      .listRecords({ days: 30 })
      .then((res) => setHistory(res.data))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  useEffect(() => {
    if (!feedback) return
    const timer = setTimeout(() => setFeedback(null), 8000)
    return () => clearTimeout(timer)
  }, [feedback])

  const handleSubmitVital = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setMessage('')
    setFeedback(null)
    try {
      const extra_data: Record<string, unknown> = {}
      if (recordType === 'blood_pressure') {
        extra_data.systolic = parseFloat(systolic)
        extra_data.diastolic = parseFloat(diastolic)
      }
      if (recordType === 'blood_glucose') {
        extra_data.type = glucoseContext
      }
      if (note.trim()) {
        extra_data.note = note.trim()
      }

      const recordedIso = new Date(recordedAt).toISOString()
      const { data } = await healthApi.createRecord({
        record_type: recordType,
        value: recordType === 'blood_pressure' ? parseFloat(systolic) : parseFloat(value),
        unit: selectedType?.unit || '',
        extra_data,
        recorded_at: recordedIso,
      })
      const result = data as HealthRecordCreateResult
      setFeedback(result.feedback)
      setValue('')
      setSystolic('')
      setDiastolic('')
      setNote('')
      setRecordedAt(toLocalDatetimeValue())
      loadHistory()
    } catch {
      setMessage('录入失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除这条记录吗？')) return
    setDeletingId(id)
    try {
      await healthApi.deleteRecord(id)
      loadHistory()
    } catch {
      setMessage('删除失败，请重试')
    } finally {
      setDeletingId(null)
    }
  }

  const handleSubmitLifestyle = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setFeedback(null)
    try {
      await healthApi.createLifestyle({ log_type: lifestyleType, content })
      setMessage('生活方式记录已保存')
      setContent('')
    } catch {
      setMessage('保存失败')
    } finally {
      setLoading(false)
    }
  }

  const feedbackStyle = feedback?.alert_level
    ? FEEDBACK_STYLES[feedback.alert_level] || FEEDBACK_STYLES.green
    : FEEDBACK_STYLES.green

  return (
    <div className="space-y-4">
      <div className="flex bg-white rounded-xl p-1 shadow-sm">
        <button
          onClick={() => setTab('vital')}
          className={`flex-1 py-2 rounded-lg text-sm font-medium ${tab === 'vital' ? 'bg-primary text-white' : 'text-gray-500'}`}
        >
          生理指标
        </button>
        <button
          onClick={() => setTab('lifestyle')}
          className={`flex-1 py-2 rounded-lg text-sm font-medium ${tab === 'lifestyle' ? 'bg-primary text-white' : 'text-gray-500'}`}
        >
          生活方式
        </button>
      </div>

      {feedback && tab === 'vital' && (
        <div className={`p-4 rounded-xl border ${feedbackStyle.bg} ${feedbackStyle.border}`}>
          <p className={`font-medium ${feedbackStyle.text}`}>{feedback.message}</p>
          {feedback.reference_range && (
            <p className={`text-sm mt-1 ${feedbackStyle.text} opacity-80`}>
              参考范围：{feedback.reference_range}
            </p>
          )}
          {feedback.alert_id && (
            <Link to="/alerts" className="inline-block text-sm text-primary mt-2 underline">
              查看预警详情
            </Link>
          )}
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="block text-xs text-gray-500 mt-2"
          >
            继续录入
          </button>
        </div>
      )}

      {message && !feedback && (
        <div
          className={`p-3 rounded-xl text-sm ${message.includes('成功') || message.includes('已保存') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}
        >
          {message}
        </div>
      )}

      {tab === 'vital' ? (
        <>
          <form onSubmit={handleSubmitVital} className="bg-white rounded-2xl p-4 shadow-sm space-y-4">
            <div>
              <label className="text-sm text-gray-600">指标类型</label>
              <div className="flex flex-wrap gap-2 mt-2">
                {RECORD_TYPES.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setRecordType(t.value)}
                    className={`px-3 py-2 rounded-full text-sm border ${
                      recordType === t.value ? 'bg-primary text-white border-primary' : 'border-gray-200'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {recordType === 'blood_glucose' && (
              <div>
                <label className="text-sm text-gray-600">测量场景</label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {GLUCOSE_CONTEXTS.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      onClick={() => setGlucoseContext(c.value)}
                      className={`px-3 py-2 rounded-full text-sm border ${
                        glucoseContext === c.value ? 'bg-primary text-white border-primary' : 'border-gray-200'
                      }`}
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
                  <label className="text-sm text-gray-600">收缩压</label>
                  <input
                    type="number"
                    inputMode="decimal"
                    value={systolic}
                    onChange={(e) => setSystolic(e.target.value)}
                    className="w-full mt-1 px-4 py-3 border rounded-xl"
                    required
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600">舒张压</label>
                  <input
                    type="number"
                    inputMode="decimal"
                    value={diastolic}
                    onChange={(e) => setDiastolic(e.target.value)}
                    className="w-full mt-1 px-4 py-3 border rounded-xl"
                    required
                  />
                </div>
              </div>
            ) : (
              <div>
                <label className="text-sm text-gray-600">数值 ({selectedType?.unit})</label>
                <input
                  type="number"
                  inputMode="decimal"
                  step="0.1"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  className="w-full mt-1 px-4 py-3 border rounded-xl"
                  required
                />
              </div>
            )}

            <div>
              <label className="text-sm text-gray-600">测量时间</label>
              <input
                type="datetime-local"
                value={recordedAt}
                onChange={(e) => setRecordedAt(e.target.value)}
                className="w-full mt-1 px-4 py-3 border rounded-xl"
                required
              />
            </div>

            <div>
              <label className="text-sm text-gray-600">备注（可选）</label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="如：早餐吃了包子"
                className="w-full mt-1 px-4 py-3 border rounded-xl"
              />
            </div>

            {previewRange && (
              <p className="text-xs text-gray-500 bg-gray-50 px-3 py-2 rounded-lg">
                参考范围：{previewRange}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary text-white py-3 rounded-xl font-medium"
            >
              {loading ? '提交中...' : '提交记录'}
            </button>
          </form>

          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <h3 className="font-semibold mb-3">最近记录</h3>
            {historyLoading ? (
              <p className="text-sm text-gray-400 text-center py-4">加载中...</p>
            ) : history.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">暂无记录</p>
            ) : (
              <div className="space-y-2">
                {history.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center justify-between py-3 border-b border-gray-50 last:border-0"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{formatRecordLabel(r)}</span>
                        {r.is_abnormal && (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">异常</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{formatDateTime(r.recorded_at)}</p>
                      {r.extra_data?.note && (
                        <p className="text-xs text-gray-400 mt-0.5 truncate">{r.extra_data.note}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-3 ml-2">
                      <span className={`text-sm font-medium whitespace-nowrap ${r.is_abnormal ? 'text-danger' : ''}`}>
                        {formatRecordValue(r)}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleDelete(r.id)}
                        disabled={deletingId === r.id}
                        className="text-xs text-gray-400 hover:text-red-500 disabled:opacity-50"
                      >
                        {deletingId === r.id ? '...' : '删除'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : (
        <form onSubmit={handleSubmitLifestyle} className="bg-white rounded-2xl p-4 shadow-sm space-y-4">
          <div className="flex gap-2">
            {LIFESTYLE_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => setLifestyleType(t.value)}
                className={`px-3 py-2 rounded-full text-sm border ${
                  lifestyleType === t.value ? 'bg-primary text-white border-primary' : 'border-gray-200'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="描述您的饮食、运动或作息情况..."
            className="w-full px-4 py-3 border rounded-xl h-32 resize-none"
            required
          />
          <button type="submit" disabled={loading} className="w-full bg-primary text-white py-3 rounded-xl font-medium">
            {loading ? '保存中...' : '保存记录'}
          </button>
        </form>
      )}
    </div>
  )
}
