import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi, patientApi } from '../api/client'

const DISEASE_LABELS: Record<string, string> = {
  diabetes_type2: '2型糖尿病',
  hypertension: '高血压',
  hyperlipidemia: '高血脂',
  copd: '慢阻肺',
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const [user, setUser] = useState<Record<string, unknown> | null>(null)
  const [patient, setPatient] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    authApi.me().then((res) => setUser(res.data))
    patientApi.getProfile().then((res) => setPatient(res.data)).catch(() => {})
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    navigate('/login')
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center text-3xl">
            👤
          </div>
          <div>
            <h2 className="font-bold text-lg">{user?.full_name as string}</h2>
            <p className="text-sm text-gray-500">{user?.email as string}</p>
          </div>
        </div>
      </div>

      {patient && (
        <div className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
          <h3 className="font-semibold">健康档案</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">性别</span><p>{patient.gender as string || '-'}</p></div>
            <div><span className="text-gray-500">出生日期</span><p>{patient.birth_date as string || '-'}</p></div>
            <div><span className="text-gray-500">身高</span><p>{patient.height_cm ? `${patient.height_cm}cm` : '-'}</p></div>
            <div><span className="text-gray-500">体重</span><p>{patient.weight_kg ? `${patient.weight_kg}kg` : '-'}</p></div>
          </div>
          <div>
            <span className="text-gray-500 text-sm">慢病类型</span>
            <div className="flex flex-wrap gap-2 mt-1">
              {((patient.diseases as string[]) || []).map((d) => (
                <span key={d} className="px-2 py-1 bg-primary/10 text-primary text-xs rounded-full">
                  {DISEASE_LABELS[d] || d}
                </span>
              ))}
            </div>
          </div>
          {patient.medications ? (
            <div>
              <span className="text-gray-500 text-sm">当前用药</span>
              <p className="text-sm mt-1">{String(patient.medications)}</p>
            </div>
          ) : null}
          <Link to="/setup" className="text-primary text-sm">编辑档案 →</Link>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
        <Link to="/plans" className="block px-4 py-3 border-b text-sm hover:bg-gray-50">管理方案</Link>
        <Link to="/followups" className="block px-4 py-3 border-b text-sm hover:bg-gray-50">随访任务</Link>
        <Link to="/documents" className="block px-4 py-3 border-b text-sm hover:bg-gray-50">体检报告</Link>
        <Link to="/knowledge" className="block px-4 py-3 text-sm hover:bg-gray-50">知识图谱</Link>
      </div>

      <button
        onClick={handleLogout}
        className="w-full bg-white text-danger py-3 rounded-xl shadow-sm font-medium"
      >
        退出登录
      </button>

      <p className="text-xs text-gray-400 text-center">
        本平台提供的健康建议仅供参考，不能替代专业医疗诊断和治疗。
      </p>
    </div>
  )
}
