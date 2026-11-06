import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'
import {
  BellIcon,
  ChevronRightIcon,
  ClipboardIcon,
  FileTextIcon,
  SettingsIcon,
  UserIcon,
} from '../components/icons'
import { useAlert } from '../context/AlertContext'
import { DISEASE_LABELS } from '../lib/types'

function calcAge(birth?: string | null): number | null {
  if (!birth) return null
  const year = Number(birth.slice(0, 4))
  if (!year) return null
  const age = new Date().getFullYear() - year
  return age > 0 && age < 130 ? age : null
}

const MENU = [
  { to: '/me/profile', label: '健康档案', Icon: ClipboardIcon },
  { to: '/me/plans', label: '管理方案', Icon: FileTextIcon },
  { to: '/me/alerts', label: '预警记录', Icon: BellIcon },
  { to: '/me/settings', label: '设置', Icon: SettingsIcon },
]

/** 我的页（规格 §6.5）。 */
export default function ProfilePage() {
  const { user, patient } = useAlert()
  const navigate = useNavigate()
  const [logoutOpen, setLogoutOpen] = useState(false)

  const age = calcAge(patient?.birth_date)
  const diseases = patient?.diseases ?? []
  const subline = [
    age != null ? `${age} 岁` : '年龄未填写',
    diseases.length ? diseases.map((d) => DISEASE_LABELS[d] ?? d).join(' · ') : '慢病未填写',
  ].join(' · ')

  const doLogout = async () => {
    try {
      await authApi.logout()
    } catch {
      /* 后端为空实现，忽略 */
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    navigate('/login', { replace: true })
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <div className="rounded-card bg-white p-5 shadow-card">
        <div className="flex items-center gap-4">
          <span className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary-deep">
            <UserIcon size={36} />
          </span>
          <div className="min-w-0">
            <p className="t-h1 truncate">{user?.full_name || '未登录'}</p>
            <p className="t-cap mt-1 text-ink-soft">{subline}</p>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-card bg-white shadow-card">
        {MENU.map(({ to, label, Icon }) => (
          <Link
            key={to}
            to={to}
            className="flex min-h-[64px] items-center gap-3 border-b border-line px-5 last:border-0"
          >
            <Icon size={24} className="text-primary-deep" />
            <span className="t-body flex-1">{label}</span>
            <ChevronRightIcon size={22} className="text-ink-soft" />
          </Link>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setLogoutOpen(true)}
        className="flex min-h-[64px] w-full items-center justify-center rounded-card bg-white px-5 shadow-card"
      >
        <span className="t-body text-level-red">退出登录</span>
      </button>

      <p className="t-cap text-center text-ink-soft">
        本平台提供的健康建议仅供参考，不能替代专业医疗诊断和治疗。
      </p>

      <ConfirmDialog
        open={logoutOpen}
        title="确认退出登录？"
        message="退出后需要重新登录才能继续使用。"
        confirmLabel="退出"
        danger
        onConfirm={() => void doLogout()}
        onCancel={() => setLogoutOpen(false)}
      />
    </div>
  )
}
