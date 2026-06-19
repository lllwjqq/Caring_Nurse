import { useEffect, useState } from 'react'
import { featureApi } from '../api/client'

export default function PlansPage() {
  const [plans, setPlans] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    featureApi.listCarePlans()
      .then((res) => setPlans(res.data))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center py-10 text-gray-400">加载中...</div>

  if (plans.length === 0) {
    return (
      <div className="bg-white rounded-2xl p-8 text-center shadow-sm">
        <div className="text-4xl mb-2">📋</div>
        <p className="text-gray-500 mb-4">暂无管理方案</p>
        <p className="text-sm text-gray-400">前往「智能问诊」说"请为我制定管理方案"即可生成</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {plans.map((plan) => {
        const diet = plan.diet_plan as { items?: string[] } | null
        const exercise = plan.exercise_plan as { items?: string[] } | null
        const monitoring = plan.monitoring_plan as { items?: string[] } | null

        return (
          <div key={plan.id as number} className="bg-white rounded-2xl p-4 shadow-sm">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold">{plan.title as string}</h3>
              <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                {plan.status as string}
              </span>
            </div>

            {diet?.items && (
              <div className="mb-3">
                <h4 className="text-sm font-medium text-gray-600 mb-1">🥗 饮食建议</h4>
                <ul className="text-sm space-y-1">
                  {diet.items.map((item, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-safe">✓</span>{item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {exercise?.items && (
              <div className="mb-3">
                <h4 className="text-sm font-medium text-gray-600 mb-1">🏃 运动建议</h4>
                <ul className="text-sm space-y-1">
                  {exercise.items.map((item, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-safe">✓</span>{item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {monitoring?.items && (
              <div className="mb-3">
                <h4 className="text-sm font-medium text-gray-600 mb-1">📊 监测计划</h4>
                <ul className="text-sm space-y-1">
                  {monitoring.items.map((item, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-primary">•</span>{item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {plan.medication_notes ? (
              <p className="text-xs text-gray-500 mt-2 border-t pt-2">
                💊 {String(plan.medication_notes)}
              </p>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
