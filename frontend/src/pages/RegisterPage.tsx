import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    email: '',
    password: '',
    full_name: '',
    agreed_disclaimer: false,
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.agreed_disclaimer) {
      setError('请先同意医疗免责声明')
      return
    }
    setLoading(true)
    setError('')
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
    <div className="flex min-h-screen items-center justify-center bg-mist px-4 py-6">
      <div className="w-full max-w-shell rounded-card bg-white p-6 shadow-card">
        <h1 className="t-h2 mb-5 text-center">注册账号</h1>

        <form onSubmit={handleRegister} className="space-y-4">
          <input
            placeholder="姓名"
            aria-label="姓名"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            className="t-body w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
            required
          />
          <input
            type="email"
            placeholder="邮箱"
            aria-label="邮箱"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="t-body w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
            required
          />
          <input
            type="password"
            placeholder="密码（至少6位）"
            aria-label="密码"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="t-body w-full rounded-btn border border-line px-4 py-3"
            style={{ minHeight: 48 }}
            minLength={6}
            required
          />

          <label className="t-cap flex items-start gap-2 text-ink-soft">
            <input
              type="checkbox"
              checked={form.agreed_disclaimer}
              onChange={(e) => setForm({ ...form, agreed_disclaimer: e.target.checked })}
              className="mt-1 h-5 w-5"
            />
            <span>
              我已阅读并同意医疗免责声明：本平台提供的健康建议仅供参考，不能替代专业医疗诊断和治疗，请遵医嘱。
            </span>
          </label>

          {error && <p className="t-cap text-level-red">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary w-full"
            style={{ minHeight: 56 }}
          >
            {loading ? '注册中…' : '注册'}
          </button>
        </form>

        <p className="t-cap mt-4 text-center text-ink-soft">
          已有账号？
          <Link to="/login" className="text-primary-deep">
            登录
          </Link>
        </p>
      </div>
    </div>
  )
}
