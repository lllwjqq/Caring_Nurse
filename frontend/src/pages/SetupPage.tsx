import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { patientApi } from '../api/client'
import { DISEASE_LABELS } from '../lib/types'

const DISEASES = Object.entries(DISEASE_LABELS)

export default function SetupPage() {
  const navigate = useNavigate()
  const [gender, setGender] = useState('男')
  const [birthDate, setBirthDate] = useState('')
  const [height, setHeight] = useState('')
  const [weight, setWeight] = useState('')
  const [diseases, setDiseases] = useState<string[]>([])
  const [allergies, setAllergies] = useState('')
  const [medications, setMedications] = useState('')
  const [emergencyContact, setEmergencyContact] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const toggleDisease = (key: string) => {
    setDiseases((prev) =>
      prev.includes(key) ? prev.filter((d) => d !== key) : [...prev, key],
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await patientApi.setupProfile({
        gender,
        birth_date: birthDate || null,
        height_cm: height ? Number(height) : null,
        weight_kg: weight ? Number(weight) : null,
        diseases,
        allergies: allergies || null,
        medications: medications || null,
        emergency_contact: emergencyContact || null,
      })
      navigate('/')
    } catch {
      setError('建档失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-mist px-5 py-6">
      <div className="mx-auto w-full max-w-shell">
        <h1 className="t-h1 mb-1">慢病档案建档</h1>
        <p className="t-cap mb-6 text-ink-soft">
          请完善您的健康档案，以便为您提供个性化管理方案
        </p>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-card bg-white p-5 shadow-card">
          <div>
            <label className="t-cap text-ink-soft" htmlFor="setup-gender">
              性别
            </label>
            <select
              id="setup-gender"
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line bg-white px-4 py-3"
              style={{ minHeight: 48 }}
            >
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
          </div>

          <div>
            <label className="t-cap text-ink-soft" htmlFor="setup-birth">
              出生日期
            </label>
            <input
              id="setup-birth"
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="t-cap text-ink-soft" htmlFor="setup-height">
                身高（cm）
              </label>
              <input
                id="setup-height"
                type="number"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
                style={{ minHeight: 48 }}
              />
            </div>
            <div>
              <label className="t-cap text-ink-soft" htmlFor="setup-weight">
                体重（kg）
              </label>
              <input
                id="setup-weight"
                type="number"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
                style={{ minHeight: 48 }}
              />
            </div>
          </div>

          <div>
            <span className="t-cap text-ink-soft">慢病类型（可多选）</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {DISEASES.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggleDisease(value)}
                  aria-pressed={diseases.includes(value)}
                  className={`t-body rounded-full border px-4 ${
                    diseases.includes(value)
                      ? 'bg-primary-deep text-white'
                      : 'border-line bg-white text-ink'
                  }`}
                  style={{ minHeight: 48 }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="t-cap text-ink-soft" htmlFor="setup-allergies">
              过敏史
            </label>
            <input
              id="setup-allergies"
              value={allergies}
              onChange={(e) => setAllergies(e.target.value)}
              placeholder="如：青霉素"
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
            />
          </div>

          <div>
            <label className="t-cap text-ink-soft" htmlFor="setup-meds">
              当前用药
            </label>
            <input
              id="setup-meds"
              value={medications}
              onChange={(e) => setMedications(e.target.value)}
              placeholder="如：二甲双胍 0.5g bid"
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
            />
          </div>

          <div>
            <label className="t-cap text-ink-soft" htmlFor="setup-contact">
              紧急联系人电话
            </label>
            <input
              id="setup-contact"
              value={emergencyContact}
              onChange={(e) => setEmergencyContact(e.target.value)}
              placeholder="如：13800138000"
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
            />
          </div>

          {error && <p className="t-cap text-level-red">{error}</p>}

          <button
            type="submit"
            disabled={loading || diseases.length === 0}
            className="btn btn-primary w-full"
            style={{ minHeight: 56 }}
          >
            {loading ? '保存中…' : '完成建档'}
          </button>
        </form>
      </div>
    </div>
  )
}
