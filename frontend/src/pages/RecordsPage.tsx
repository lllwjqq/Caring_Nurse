import { useState } from 'react'
import { healthApi } from '../api/client'

const RECORD_TYPES = [
  { value: 'blood_glucose', label: '血糖', unit: 'mmol/L' },
  { value: 'blood_pressure', label: '血压', unit: 'mmHg' },
  { value: 'weight', label: '体重', unit: 'kg' },
  { value: 'blood_lipid', label: '血脂', unit: 'mmol/L' },
  { value: 'spo2', label: '血氧', unit: '%' },
]

const LIFESTYLE_TYPES = [
  { value: 'diet', label: '饮食' },
  { value: 'exercise', label: '运动' },
  { value: 'sleep', label: '作息' },
]

export default function RecordsPage() {
  const [tab, setTab] = useState<'vital' | 'lifestyle'>('vital')
  const [recordType, setRecordType] = useState('blood_glucose')
  const [value, setValue] = useState('')
  const [systolic, setSystolic] = useState('')
  const [diastolic, setDiastolic] = useState('')
  const [lifestyleType, setLifestyleType] = useState('diet')
  const [content, setContent] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  const selectedType = RECORD_TYPES.find((t) => t.value === recordType)

  const handleSubmitVital = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setMessage('')
    try {
      const extra_data: Record<string, unknown> = {}
      if (recordType === 'blood_pressure') {
        extra_data.systolic = parseFloat(systolic)
        extra_data.diastolic = parseFloat(diastolic)
      }
      await healthApi.createRecord({
        record_type: recordType,
        value: recordType === 'blood_pressure' ? parseFloat(systolic) : parseFloat(value),
        unit: selectedType?.unit || '',
        extra_data,
      })
      setMessage('录入成功！系统已自动分析指标。')
      setValue('')
      setSystolic('')
      setDiastolic('')
    } catch {
      setMessage('录入失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitLifestyle = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
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

      {message && (
        <div className={`p-3 rounded-xl text-sm ${message.includes('成功') || message.includes('已保存') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
          {message}
        </div>
      )}

      {tab === 'vital' ? (
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

          {recordType === 'blood_pressure' ? (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-gray-600">收缩压</label>
                <input
                  type="number"
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
                step="0.1"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-full mt-1 px-4 py-3 border rounded-xl"
                required
              />
            </div>
          )}

          <button type="submit" disabled={loading} className="w-full bg-primary text-white py-3 rounded-xl font-medium">
            {loading ? '提交中...' : '提交记录'}
          </button>
        </form>
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
            保存记录
          </button>
        </form>
      )}
    </div>
  )
}
