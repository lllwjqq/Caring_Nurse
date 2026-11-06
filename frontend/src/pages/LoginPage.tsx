import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'

export default function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('demo@nurse.com')
  const [password, setPassword] = useState('demo123')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const { data } = await authApi.login({ email, password })
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      navigate('/')
    } catch {
      setError('登录失败，请检查邮箱和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-mist px-4">
      <div className="w-full max-w-shell rounded-card bg-white p-6 shadow-card">
        <div className="mb-6 text-center">
          <h1 className="t-h1 text-ink">贴心小护士</h1>
          <p className="t-cap mt-1 text-ink-soft">多智能体个性化慢病管理助手</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="t-cap text-ink-soft" htmlFor="login-email">
              邮箱
            </label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
              required
            />
          </div>
          <div>
            <label className="t-cap text-ink-soft" htmlFor="login-password">
              密码
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="t-body mt-1 w-full rounded-btn border border-line px-4 py-3"
              style={{ minHeight: 48 }}
              required
            />
          </div>

          {error && <p className="t-cap text-level-red">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary w-full"
            style={{ minHeight: 56 }}
          >
            {loading ? '登录中…' : '登录'}
          </button>
        </form>

        <p className="t-cap mt-4 text-center text-ink-soft">
          还没有账号？
          <Link to="/register" className="text-primary-deep">
            立即注册
          </Link>
        </p>
        <p className="t-cap mt-2 text-center text-ink-soft">演示账号：demo@nurse.com / demo123</p>
      </div>
    </div>
  )
}
