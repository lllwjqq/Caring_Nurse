import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { featureApi } from '../../api/client'
import SectionCard from '../../components/SectionCard'
import { PlayIcon } from '../../components/icons'
import { useVoice } from '../../context/VoiceContext'
import type { CarePlanItem } from '../../lib/types'
import { formatDateTime } from '../../constants/healthRecords'

/** 管理方案子页（规格 §6.5.2）。 */
export default function CarePlansPage() {
  const voice = useVoice()
  const [plans, setPlans] = useState<CarePlanItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    featureApi
      .listCarePlans()
      .then((res) => setPlans(res.data as CarePlanItem[]))
      .catch(() => setPlans([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="px-5 py-8 text-center">
        <span className="t-body text-ink-soft">正在加载管理方案…</span>
      </div>
    )
  }

  if (!plans.length) {
    return (
      <div className="px-5 py-5">
        <div className="rounded-card bg-white p-6 text-center shadow-card">
          <p className="t-body">还没有管理方案</p>
          <p className="t-cap mt-2 text-ink-soft">去问诊页说「请为我制定管理方案」</p>
          <Link to="/" className="btn btn-primary mt-4 w-full" style={{ minHeight: 48 }}>
            去问诊
          </Link>
        </div>
      </div>
    )
  }

  const plan = plans[0]
  const groups = [
    { key: 'diet', title: '饮食', items: plan.diet_plan?.items ?? [] },
    { key: 'exercise', title: '运动', items: plan.exercise_plan?.items ?? [] },
    { key: 'monitor', title: '监测', items: plan.monitoring_plan?.items ?? [] },
  ]

  return (
    <div className="space-y-5 px-5 py-5">
      <p className="t-cap text-ink-soft">
        {plan.title} · 生成于 {formatDateTime(plan.created_at)}
      </p>

      {groups.map((group) => (
        <SectionCard key={group.key} title={group.title}>
          {group.items.length === 0 ? (
            <p className="t-body text-ink-soft">暂无内容</p>
          ) : (
            <ul className="space-y-1">
              {group.items.map((item, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="t-body flex-1">{item}</span>
                  <button
                    type="button"
                    onClick={() => void voice.speak(item)}
                    aria-label={`朗读 ${item}`}
                    className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-primary-deep"
                  >
                    <PlayIcon size={20} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      ))}

      {plan.medication_notes && (
        <div className="rounded-card border-l-4 border-primary bg-primary/10 p-4">
          <p className="t-cap text-primary-deep">{plan.medication_notes}</p>
        </div>
      )}
    </div>
  )
}
