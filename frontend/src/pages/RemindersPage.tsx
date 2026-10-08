import { useEffect, useState } from 'react'
import { reminderApi } from '../api/client'

interface Reminder {
  id: number
  medication_name: string
  brand_name?: string | null
  spec?: string | null
  dose?: number | null
  dose_unit?: string | null
  frequency: string
  times_of_day: string[] | null
  route?: string | null
  timing_note?: string | null
  notes?: string | null
  active: boolean
}

const FREQ_LABELS: Record<string, string> = {
  qd: '每日1次',
  bid: '每日2次',
  tid: '每日3次',
  qid: '每日4次',
  q8h: '每8小时',
  qn: '睡前',
  prn: '按需',
}

const FREQUENCIES = [
  { value: 'qd', label: '每日1次' },
  { value: 'bid', label: '每日2次' },
  { value: 'tid', label: '每日3次' },
  { value: 'qid', label: '每日4次' },
  { value: 'q8h', label: '每8小时' },
  { value: 'qn', label: '睡前' },
  { value: 'prn', label: '按需' },
]

function doseText(r: Reminder): string {
  const d = `${r.dose ?? ''}${r.dose_unit ?? ''}`.trim()
  return d || '按医嘱'
}

function sortByTime(a: Reminder, b: Reminder): number {
  const ta = a.times_of_day?.[0] ?? '99:99'
  const tb = b.times_of_day?.[0] ?? '99:99'
  return ta.localeCompare(tb)
}

export default function RemindersPage() {
  const [today, setToday] = useState<Reminder[]>([])
  const [all, setAll] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ medication_name: '', dose: '', dose_unit: '', frequency: 'qd', timing_note: '' })
  const [submitting, setSubmitting] = useState(false)

  const load = () => {
    Promise.all([reminderApi.today(), reminderApi.list()])
      .then(([t, a]) => {
        setToday(t.data)
        setAll(a.data)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleToggle = async (r: Reminder) => {
    await reminderApi.update(r.id, { active: !r.active })
    load()
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除该提醒吗？')) return
    await reminderApi.remove(id)
    load()
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.medication_name.trim()) return
    setSubmitting(true)
    setMessage('')
    try {
      await reminderApi.create({
        medication_name: form.medication_name.trim(),
        dose: form.dose === '' ? undefined : Number(form.dose),
        dose_unit: form.dose_unit.trim() || undefined,
        frequency: form.frequency,
        timing_note: form.timing_note.trim() || undefined,
      })
      setForm({ medication_name: '', dose: '', dose_unit: '', frequency: 'qd', timing_note: '' })
      setShowForm(false)
      setMessage('已添加服药提醒')
      load()
    } catch {
      setMessage('添加失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">处方照片自动生成提醒，或手动添加</p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-sm bg-primary text-white px-3 py-1.5 rounded-full"
        >
          {showForm ? '取消' : '+ 手动添加'}
        </button>
      </div>

      {message && <p className="text-sm text-primary">{message}</p>}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
          <div>
            <label className="text-sm text-gray-600">药名</label>
            <input
              value={form.medication_name}
              onChange={(e) => setForm((f) => ({ ...f, medication_name: e.target.value }))}
              placeholder="如：阿司匹林肠溶片"
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-gray-600">单次剂量</label>
              <input
                type="number"
                value={form.dose}
                onChange={(e) => setForm((f) => ({ ...f, dose: e.target.value }))}
                placeholder="如：1"
                className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="text-sm text-gray-600">单位</label>
              <input
                value={form.dose_unit}
                onChange={(e) => setForm((f) => ({ ...f, dose_unit: e.target.value }))}
                placeholder="片 / mg"
                className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-gray-600">频次</label>
              <select
                value={form.frequency}
                onChange={(e) => setForm((f) => ({ ...f, frequency: e.target.value }))}
                className="w-full mt-1 px-3 py-2 border rounded-lg text-sm bg-white"
              >
                {FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-600">时点（可选）</label>
              <input
                value={form.timing_note}
                onChange={(e) => setForm((f) => ({ ...f, timing_note: e.target.value }))}
                placeholder="饭前 / 饭后 / 睡前"
                className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-primary text-white py-3 rounded-xl font-medium disabled:opacity-50"
          >
            {submitting ? '保存中...' : '保存提醒'}
          </button>
        </form>
      )}

      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <h3 className="font-semibold mb-3">今日服药</h3>
        {loading ? (
          <p className="text-sm text-gray-400 text-center py-4">加载中...</p>
        ) : today.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">今日暂无服药安排</p>
        ) : (
          <div className="space-y-2">
            {today.slice().sort(sortByTime).map((r) => (
              <div key={r.id} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{r.medication_name}</p>
                  <p className="text-xs text-gray-500">
                    {doseText(r)} · {(r.times_of_day || []).join('、')}
                    {r.timing_note ? ` · ${r.timing_note}` : ''}
                  </p>
                </div>
                <span className="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded-full whitespace-nowrap">
                  {FREQ_LABELS[r.frequency] || r.frequency}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <h3 className="font-semibold mb-3">全部提醒</h3>
        {loading ? (
          <p className="text-sm text-gray-400 text-center py-4">加载中...</p>
        ) : all.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">暂无提醒，上传处方或手动添加</p>
        ) : (
          <div className="space-y-3">
            {all.map((r) => (
              <div key={r.id} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-medium ${r.active ? '' : 'text-gray-400 line-through'}`}>
                    {r.medication_name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {doseText(r)} · {(r.times_of_day || []).join('、') || '按需'}
                  </p>
                </div>
                <div className="flex items-center gap-2 ml-2">
                  <button
                    type="button"
                    onClick={() => handleToggle(r)}
                    className={`text-xs px-2 py-1 rounded-full ${r.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}
                  >
                    {r.active ? '进行中' : '已暂停'}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(r.id)}
                    className="text-xs text-gray-400 hover:text-red-500"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
