import { useEffect, useState } from 'react'
import { featureApi } from '../api/client'

export default function FollowupPage() {
  const [followups, setFollowups] = useState<Array<Record<string, unknown>>>([])
  const [responses, setResponses] = useState<Record<number, Record<string, unknown>>>({})
  const [loading, setLoading] = useState(true)

  const load = () => {
    featureApi.listFollowups()
      .then((res) => setFollowups(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleSubmit = async (id: number) => {
    await featureApi.submitFollowup(id, responses[id] || {})
    load()
  }

  if (loading) return <div className="text-center py-10 text-gray-400">加载中...</div>

  const pending = followups.filter((f) => f.status === 'pending')

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">定期随访帮助评估您的慢病管理依从性</p>

      {pending.length === 0 && followups.length === 0 && (
        <div className="bg-white rounded-2xl p-8 text-center shadow-sm">
          <p className="text-gray-500">暂无随访任务</p>
        </div>
      )}

      {pending.map((fu) => {
        const questions = (fu.questions as Array<Record<string, unknown>>) || []
        return (
          <div key={fu.id as number} className="bg-white rounded-2xl p-4 shadow-sm">
            <h3 className="font-semibold">{fu.title as string}</h3>
            <div className="space-y-4 mt-4">
              {questions.map((q) => (
                <div key={q.id as string}>
                  <p className="text-sm text-gray-700 mb-2">{q.text as string}</p>
                  {q.type === 'boolean' && (
                    <div className="flex gap-2">
                      {['是', '否'].map((opt) => (
                        <button
                          key={opt}
                          onClick={() =>
                            setResponses((r) => ({
                              ...r,
                              [fu.id as number]: { ...r[fu.id as number], [q.id as string]: opt === '是' },
                            }))
                          }
                          className={`px-4 py-2 rounded-lg text-sm border ${
                            responses[fu.id as number]?.[q.id as string] === (opt === '是')
                              ? 'bg-primary text-white border-primary'
                              : 'border-gray-200'
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  )}
                  {q.type === 'choice' && (
                    <div className="flex flex-wrap gap-2">
                      {((q.options as string[]) || []).map((opt) => (
                        <button
                          key={opt}
                          onClick={() =>
                            setResponses((r) => ({
                              ...r,
                              [fu.id as number]: { ...r[fu.id as number], [q.id as string]: opt },
                            }))
                          }
                          className={`px-3 py-2 rounded-lg text-sm border ${
                            responses[fu.id as number]?.[q.id as string] === opt
                              ? 'bg-primary text-white border-primary'
                              : 'border-gray-200'
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  )}
                  {q.type === 'scale' && (
                    <div className="flex gap-2">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          onClick={() =>
                            setResponses((r) => ({
                              ...r,
                              [fu.id as number]: { ...r[fu.id as number], [q.id as string]: n },
                            }))
                          }
                          className={`w-10 h-10 rounded-lg text-sm border ${
                            responses[fu.id as number]?.[q.id as string] === n
                              ? 'bg-primary text-white border-primary'
                              : 'border-gray-200'
                          }`}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <button
              onClick={() => handleSubmit(fu.id as number)}
              className="w-full mt-4 bg-primary text-white py-3 rounded-xl font-medium"
            >
              提交随访
            </button>
          </div>
        )
      })}

      {followups.filter((f) => f.status === 'completed').map((fu) => (
        <div key={fu.id as number} className="bg-gray-50 rounded-2xl p-4">
          <h3 className="font-medium text-gray-600">{fu.title as string}</h3>
          <p className="text-sm text-gray-500 mt-1">
            已完成 · 依从性评分：{((fu.adherence_score as number) * 100).toFixed(0)}%
          </p>
        </div>
      ))}
    </div>
  )
}
