import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { patientApi } from '../api/client'

const DISEASES = [
  { value: 'diabetes_type2', label: '2型糖尿病' },
  { value: 'hypertension', label: '高血压' },
  { value: 'hyperlipidemia', label: '高血脂' },
  { value: 'copd', label: '慢阻肺' },
]

export default function SetupPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    gender: '男',
    birth_date: '',
    height_cm: '',
    weight_kg: '',
    diseases: [] as string[],
    allergies: '',
    medications: '',
    emergency_contact: '',
  })
  const [loading, setLoading] = useState(false)

  const toggleDisease = (value: string) => {
    setForm((f) => ({
      ...f,
      diseases: f.diseases.includes(value)
        ? f.diseases.filter((d) => d !== value)
        : [...f.diseases, value],
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await patientApi.setupProfile({
        ...form,
        height_cm: form.height_cm ? parseFloat(form.height_cm) : null,
        weight_kg: form.weight_kg ? parseFloat(form.weight_kg) : null,
      })
      navigate('/')
    } catch {
      alert('建档失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-8">
      <div className="max-w-lg mx-auto bg-white rounded-2xl shadow p-6">
        <h1 className="text-xl font-bold mb-2">慢病档案建档</h1>
        <p className="text-gray-500 text-sm mb-6">请完善您的健康档案，以便为您提供个性化管理方案</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-gray-600">性别</label>
            <select
              value={form.gender}
              onChange={(e) => setForm({ ...form, gender: e.target.value })}
              className="w-full mt-1 px-4 py-3 border rounded-xl"
            >
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-gray-600">出生日期</label>
            <input
              type="date"
              value={form.birth_date}
              onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
              className="w-full mt-1 px-4 py-3 border rounded-xl"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-gray-600">身高(cm)</label>
              <input
                type="number"
                value={form.height_cm}
                onChange={(e) => setForm({ ...form, height_cm: e.target.value })}
                className="w-full mt-1 px-4 py-3 border rounded-xl"
              />
            </div>
            <div>
              <label className="text-sm text-gray-600">体重(kg)</label>
              <input
                type="number"
                value={form.weight_kg}
                onChange={(e) => setForm({ ...form, weight_kg: e.target.value })}
                className="w-full mt-1 px-4 py-3 border rounded-xl"
              />
            </div>
          </div>

          <div>
            <label className="text-sm text-gray-600">慢病类型（可多选）</label>
            <div className="flex flex-wrap gap-2 mt-2">
              {DISEASES.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  onClick={() => toggleDisease(d.value)}
                  className={`px-3 py-2 rounded-full text-sm border ${
                    form.diseases.includes(d.value)
                      ? 'bg-primary text-white border-primary'
                      : 'bg-white text-gray-600 border-gray-200'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <input
            placeholder="过敏史"
            value={form.allergies}
            onChange={(e) => setForm({ ...form, allergies: e.target.value })}
            className="w-full px-4 py-3 border rounded-xl"
          />
          <input
            placeholder="当前用药"
            value={form.medications}
            onChange={(e) => setForm({ ...form, medications: e.target.value })}
            className="w-full px-4 py-3 border rounded-xl"
          />
          <input
            placeholder="紧急联系人电话"
            value={form.emergency_contact}
            onChange={(e) => setForm({ ...form, emergency_contact: e.target.value })}
            className="w-full px-4 py-3 border rounded-xl"
          />

          <button
            type="submit"
            disabled={loading || form.diseases.length === 0}
            className="w-full bg-primary text-white py-3 rounded-xl font-medium disabled:opacity-50"
          >
            {loading ? '保存中...' : '完成建档'}
          </button>
        </form>
      </div>
    </div>
  )
}
