import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { diagnosisApi, patientApi } from '../../api/client'
import SectionCard from '../../components/SectionCard'
import { useToast } from '../../components/Toast'
import { useAlert } from '../../context/AlertContext'
import { DISEASE_LABELS, type DiagnosisItem } from '../../lib/types'

const DISEASES = Object.entries(DISEASE_LABELS)

const DIAGNOSIS_SOURCE_LABELS: Record<string, string> = {
  discharge_summary: '出院小结',
  outpatient_record: '门诊病历',
  prescription: '处方',
  manual: '手动',
}

function diagnosisTime(diagnosis: DiagnosisItem): number {
  const raw = diagnosis.diagnosed_at ?? diagnosis.created_at
  const time = Date.parse(raw)
  return Number.isNaN(time) ? 0 : time
}

function formatDiagnosisDate(diagnosis: DiagnosisItem): string {
  const raw = diagnosis.diagnosed_at ?? diagnosis.created_at
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).formatToParts(date)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('year')}年${get('month')}月${get('day')}日`
}

/** 健康档案子页（规格 §6.5.1）。 */
export default function HealthProfilePage() {
  const { patient, refreshPatient } = useAlert()
  const { showToast } = useToast()

  const [gender, setGender] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [height, setHeight] = useState('')
  const [weight, setWeight] = useState('')
  const [diseases, setDiseases] = useState<string[]>([])
  const [allergies, setAllergies] = useState('')
  const [medications, setMedications] = useState('')
  const [emergencyContact, setEmergencyContact] = useState('')
  const [busy, setBusy] = useState(false)

  const [diagnoses, setDiagnoses] = useState<DiagnosisItem[]>([])
  const [diagnosesLoading, setDiagnosesLoading] = useState(true)
  const [diagnosesError, setDiagnosesError] = useState(false)

  const loadDiagnoses = useCallback(async () => {
    setDiagnosesLoading(true)
    setDiagnosesError(false)
    try {
      const { data } = await diagnosisApi.list()
      const list = ((data as DiagnosisItem[]) ?? []).slice()
      list.sort((a, b) => diagnosisTime(b) - diagnosisTime(a))
      setDiagnoses(list)
    } catch {
      setDiagnosesError(true)
    } finally {
      setDiagnosesLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadDiagnoses()
  }, [loadDiagnoses])

  useEffect(() => {
    if (!patient) return
    setGender(patient.gender ?? '')
    setBirthDate(patient.birth_date ?? '')
    setHeight(patient.height_cm != null ? String(patient.height_cm) : '')
    setWeight(patient.weight_kg != null ? String(patient.weight_kg) : '')
    setDiseases(patient.diseases ?? [])
    setAllergies(patient.allergies ?? '')
    setMedications(patient.medications ?? '')
    setEmergencyContact(patient.emergency_contact ?? '')
  }, [patient])

  const toggleDisease = (key: string) => {
    setDiseases((prev) =>
      prev.includes(key) ? prev.filter((d) => d !== key) : [...prev, key],
    )
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await patientApi.updateProfile({
        gender: gender || null,
        birth_date: birthDate || null,
        height_cm: height ? Number(height) : null,
        weight_kg: weight ? Number(weight) : null,
        diseases,
        allergies: allergies || null,
        medications: medications || null,
        emergency_contact: emergencyContact || null,
      })
      await refreshPatient()
      showToast('健康档案已保存')
    } catch {
      showToast('保存失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <form onSubmit={submit} className="space-y-5">
        <div className="space-y-4 rounded-card bg-white p-5 shadow-card">
        <div>
          <label className="t-cap text-ink-soft" htmlFor="hp-gender">
            性别
          </label>
          <select
            id="hp-gender"
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            className="t-body mt-1 w-full rounded-btn border border-line bg-white px-4 py-3"
            style={{ minHeight: 48 }}
          >
            <option value="">未填写</option>
            <option value="男">男</option>
            <option value="女">女</option>
          </select>
        </div>

        <div>
          <label className="t-cap text-ink-soft" htmlFor="hp-birth">
            出生日期
          </label>
          <input
            id="hp-birth"
            type="date"
            value={birthDate}
            onChange={(e) => setBirthDate(e.target.value)}
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="t-cap text-ink-soft" htmlFor="hp-height">
              身高（cm）
            </label>
            <input
              id="hp-height"
              type="number"
              value={height}
              onChange={(e) => setHeight(e.target.value)}
              placeholder="如 170"
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
            />
          </div>
          <div>
            <label className="t-cap text-ink-soft" htmlFor="hp-weight">
              体重（kg）
            </label>
            <input
              id="hp-weight"
              type="number"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              placeholder="如 65"
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
          <label className="t-cap text-ink-soft" htmlFor="hp-allergies">
            过敏史
          </label>
          <input
            id="hp-allergies"
            value={allergies}
            onChange={(e) => setAllergies(e.target.value)}
            placeholder="如：青霉素、海鲜"
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>

        <div>
          <label className="t-cap text-ink-soft" htmlFor="hp-meds">
            长期用药
          </label>
          <input
            id="hp-meds"
            value={medications}
            onChange={(e) => setMedications(e.target.value)}
            placeholder="如：二甲双胍 0.5g bid"
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>

        <div>
          <label className="t-cap text-ink-soft" htmlFor="hp-contact">
            紧急联系人
          </label>
          <input
            id="hp-contact"
            value={emergencyContact}
            onChange={(e) => setEmergencyContact(e.target.value)}
            placeholder="如：13800138000（家属）"
            className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
          />
        </div>
      </div>

        <button type="submit" disabled={busy} className="btn btn-primary w-full" style={{ minHeight: 56 }}>
          {busy ? '保存中…' : '保存档案'}
        </button>
      </form>

      <SectionCard title="诊断记录">
        {diagnosesLoading ? (
          <p className="t-body py-2 text-ink-soft">正在加载诊断记录…</p>
        ) : diagnosesError ? (
          <div className="py-2 text-center">
            <p className="t-body text-ink-soft">诊断记录加载失败，请稍后重试</p>
            <button
              type="button"
              onClick={() => void loadDiagnoses()}
              className="btn btn-primary mt-4"
              style={{ minHeight: 48 }}
            >
              重试
            </button>
          </div>
        ) : diagnoses.length === 0 ? (
          <p className="t-body py-2 text-ink-soft">暂无诊断记录，上传病历或处方后会自动归档</p>
        ) : (
          <ol className="relative mt-1 space-y-4 pl-6">
            <span className="absolute bottom-2 left-3 top-2 w-px bg-line" aria-hidden="true" />
            {diagnoses.map((diagnosis) => {
              const sourceLabel = DIAGNOSIS_SOURCE_LABELS[diagnosis.doc_type] ?? diagnosis.doc_type
              const dateText = formatDiagnosisDate(diagnosis)
              const isCurrent = diagnosis.status === 'current'
              return (
                <li key={diagnosis.id} className="relative">
                  <span
                    className={`absolute -left-[18px] top-2 h-3 w-3 rounded-full ring-4 ring-white ${
                      isCurrent ? 'bg-primary-deep' : 'bg-ink-soft'
                    }`}
                    aria-hidden="true"
                  />
                  <div className="rounded-btn border border-line bg-mist/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <h3 className="t-h2 min-w-0 flex-1">{diagnosis.name}</h3>
                      <span
                        className={`t-cap shrink-0 rounded-full px-3 py-1 ${
                          isCurrent ? 'bg-primary/10 text-primary-deep' : 'bg-line text-ink-soft'
                        }`}
                      >
                        {isCurrent ? '当前' : '既往'}
                      </span>
                    </div>

                    {dateText && <p className="t-cap mt-1 text-ink-soft">{dateText}</p>}

                    {diagnosis.source_document_id != null ? (
                      <Link
                        to={`/record/document/${diagnosis.source_document_id}`}
                        className="t-cap mt-1 inline-flex min-h-[48px] items-center text-primary-deep underline"
                      >
                        来源：{sourceLabel}
                      </Link>
                    ) : (
                      <p className="t-cap mt-1 text-ink-soft">来源：{sourceLabel}</p>
                    )}

                    {diagnosis.notes && (
                      <p className="t-cap mt-1 line-clamp-2 text-ink-soft">{diagnosis.notes}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        )}
      </SectionCard>
    </div>
  )
}
