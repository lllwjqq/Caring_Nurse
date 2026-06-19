import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const navItems = [
  { to: '/', label: '首页', icon: '🏠' },
  { to: '/records', label: '录入', icon: '📝' },
  { to: '/chat', label: '问诊', icon: '💬' },
  { to: '/alerts', label: '预警', icon: '🔔' },
  { to: '/profile', label: '我的', icon: '👤' },
]

export default function Layout() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col min-h-screen pb-16">
      <header className="bg-gradient-to-r from-primary to-nurse text-white px-4 py-3 shadow-md sticky top-0 z-50">
        <div className="flex items-center justify-between max-w-lg mx-auto">
          <h1 className="text-lg font-bold">贴心小护士</h1>
          <button onClick={() => navigate('/plans')} className="text-sm bg-white/20 px-3 py-1 rounded-full">
            管理方案
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-lg mx-auto w-full px-4 py-4">
        <Outlet />
      </main>

      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50">
        <div className="flex justify-around max-w-lg mx-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex flex-col items-center py-2 px-3 text-xs ${isActive ? 'text-primary font-semibold' : 'text-gray-500'}`
              }
            >
              <span className="text-xl">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
