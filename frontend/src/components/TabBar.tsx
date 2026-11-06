import type { ComponentType } from 'react'
import { NavLink } from 'react-router-dom'
import { useAlert } from '../context/AlertContext'
import { ChatIcon, PillIcon, PlusCircleIcon, PulseIcon, UserIcon, type IconProps } from './icons'

interface TabItem {
  to: string
  label: string
  Icon: ComponentType<IconProps>
  end?: boolean
  badge?: boolean
}

const ITEMS: TabItem[] = [
  { to: '/', label: '问诊', Icon: ChatIcon, end: true, badge: true },
  { to: '/monitor', label: '监测', Icon: PulseIcon },
  { to: '/record', label: '录入', Icon: PlusCircleIcon },
  { to: '/medication', label: '用药', Icon: PillIcon },
  { to: '/me', label: '我的', Icon: UserIcon },
]

/** 底部 5 tab 主导航（规格 §4.3）。 */
export default function TabBar() {
  const { unreadCount } = useAlert()

  return (
    <nav
      id="tab-bar"
      aria-label="主导航"
      className="relative z-40 shrink-0 border-t border-line bg-white"
      style={{ paddingBottom: 'var(--safe-bottom)' }}
    >
      <div className="mx-auto flex h-16 max-w-shell items-stretch justify-around">
        {ITEMS.map(({ to, label, Icon, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `relative flex min-h-[64px] min-w-[64px] flex-1 flex-col items-center justify-center gap-0.5 rounded-xl transition-colors ${
                isActive ? 'text-primary-deep' : 'text-ink-soft'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`flex h-8 min-w-[44px] items-center justify-center rounded-full ${
                    isActive ? 'bg-primary/10' : ''
                  }`}
                >
                  <Icon size={26} strokeWidth={isActive ? 2.4 : 2} />
                </span>
                <span
                  className="t-cap leading-none"
                  style={{ fontWeight: isActive ? 700 : 500 }}
                >
                  {label}
                </span>
                {badge && unreadCount > 0 && (
                  <span
                    aria-label={`${unreadCount}条未读预警`}
                    className="absolute right-1/2 top-1 flex h-6 min-w-[24px] translate-x-7 items-center justify-center rounded-full bg-nurse px-1 leading-none text-white"
                  >
                    <span className="t-cap leading-none" style={{ fontWeight: 700 }}>
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
