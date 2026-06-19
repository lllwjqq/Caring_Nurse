import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '', full_name: '', agreed_disclaimer: false })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.agreed_disclaimer) {
      setError('请先同意医疗免责声明')
      return
    }
    setLoading(true)
    try {
      const { data } = await authApi.register(form)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      navigate('/setup')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-primary/10 to-nurse/10 px-4 py-8">
      <div className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-sm">
        <h1 className="text-xl font-bold text-center mb-6">注册账号</h1>
        <form onSubmit={handleRegister} className="space-y-4">
          <input
            placeholder="姓名"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl"
            required
          />
          <input
            type="email"
            placeholder="邮箱"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl"
            required
          />
          <input
            type="password"
            placeholder="密码（至少6位）"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl"
            minLength={6}
            required
          />
          <label className="flex items-start gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={form.agreed_disclaimer}
              onChange={(e) => setForm({ ...form, agreed_disclaimer: e.target.checked })}
              className="mt-1"
            />
            <span>
              我已阅读并同意医疗免责声明：本平台提供的健康建议仅供参考，不能替代专业医疗诊断和治疗，请遵医嘱。
            </span>
          </label>
          {error && <p className="text-danger text-sm">{error}</p>}
          <button type="submit" disabled={loading} className="w-full bg-primary text-white py-3 rounded-xl font-medium">
            {loading ? '注册中...' : '注册'}
          </button>
        </form>
        <p className="text-center text-sm text-gray-500 mt-4">
          已有账号？<Link to="/login" className="text-primary">登录</Link>
        </p>
      </div>
    </div>
  )
}
