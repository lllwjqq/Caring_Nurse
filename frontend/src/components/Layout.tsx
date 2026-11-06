import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAlert } from '../context/AlertContext'
import PageHeader, { type HeaderVariant } from './PageHeader'
import SosDialog from './SosDialog'
import TabBar from './TabBar'
import VoiceConfirmCard from './VoiceConfirmCard'
import VoiceOrb from './VoiceOrb'

const TAB_TITLES: Record<string, string> = {
  '/monitor': '我的健康',
  '/record': '记录健康数据',
  '/medication': '我的用药',
  '/me': '我的',
}

// 顺序敏感：更具体的子页前缀放前面
const SUBPAGES: Array<[string, string]> = [
  ['/me/settings/legal/', '免责声明'],
  ['/me/settings', '设置'],
  ['/me/profile', '健康档案'],
  ['/me/plans', '管理方案'],
  ['/me/alerts', '预警记录'],
  ['/record/document/', '确认识别结果'],
]

function headerConfig(pathname: string): { variant: HeaderVariant; title?: string } {
  if (pathname === '/') return { variant: 'identity' }

  const sub = SUBPAGES.find(([prefix]) => pathname.startsWith(prefix))
  if (sub) {
    let title = sub[1]
    if (sub[0] === '/me/settings/legal/') {
      title = pathname.split('/').pop() === 'privacy' ? '隐私政策' : '免责声明'
    }
    return { variant: 'back', title }
  }

  return { variant: 'title', title: TAB_TITLES[pathname] ?? '贴心小护士' }
}

/** App Shell（规格 §4.1）：页头 + 独立滚动的 main + TabBar + 语音球。 */
export default function Layout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { patient } = useAlert()
  const [sosOpen, setSosOpen] = useState(false)

  const config = headerConfig(pathname)

  return (
    <div id="app-shell" className="app-shell">
      <PageHeader
        variant={config.variant}
        title={config.title}
        onBack={() => navigate(-1)}
        onOpenSos={() => setSosOpen(true)}
      />

      <main id="page-main" className="page-main">
        <Outlet />
      </main>

      <TabBar />
      <VoiceOrb />
      <VoiceConfirmCard />

      <SosDialog
        open={sosOpen}
        contact={patient?.emergency_contact ?? null}
        onClose={() => setSosOpen(false)}
        onGoSetup={() => navigate('/me/profile')}
      />
    </div>
  )
}
