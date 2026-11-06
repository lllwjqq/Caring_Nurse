import { useState } from 'react'
import { Link } from 'react-router-dom'
import BigTextToggle from '../../components/BigTextToggle'
import ChangePasswordDialog from '../../components/ChangePasswordDialog'
import SectionCard from '../../components/SectionCard'
import SwitchRow from '../../components/SwitchRow'
import { ChevronRightIcon } from '../../components/icons'
import { useSettings } from '../../context/SettingsContext'
import { useVoice } from '../../context/VoiceContext'
import { useToast } from '../../components/Toast'

const APP_VERSION = '1.0.0'

/** 设置子页（规格 §6.5.4）。 */
export default function SettingsPage() {
  const { settings, update } = useSettings()
  const voice = useVoice()
  const { showToast } = useToast()
  const [pwdOpen, setPwdOpen] = useState(false)

  const resetOrb = () => {
    try {
      localStorage.removeItem('orb_position')
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event('orb-reset'))
    showToast('语音球位置已复位')
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <SectionCard title="语音">
        <SwitchRow
          label="语音播报"
          desc="收到预警或朗读内容时播放语音"
          checked={voice.enabled}
          onChange={voice.setEnabled}
        />

        <div className="py-2">
          <div className="flex items-center justify-between">
            <span className="t-body">音量</span>
            <span className="t-cap text-ink-soft">{voice.volume}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={voice.volume}
            onChange={(e) => voice.setVolume(Number(e.target.value))}
            aria-label="音量"
            className="mt-2 w-full"
            style={{ height: 48 }}
          />
        </div>

        <div className="py-2">
          <div className="flex items-center justify-between">
            <span className="t-body">语速</span>
            <span className="t-cap text-ink-soft">{voice.rate.toFixed(1)} 倍</span>
          </div>
          <input
            type="range"
            min={0.5}
            max={2}
            step={0.1}
            value={voice.rate}
            onChange={(e) => voice.setRate(Number(e.target.value))}
            aria-label="语速"
            className="mt-2 w-full"
            style={{ height: 48 }}
          />
        </div>

        <button
          type="button"
          onClick={resetOrb}
          className="flex min-h-[64px] w-full items-center justify-between border-t border-line py-2 text-left"
        >
          <span className="t-body">语音球位置</span>
          <span className="t-cap text-primary-deep">复位</span>
        </button>
      </SectionCard>

      <SectionCard title="显示">
        <BigTextToggle value={settings.bigText} onChange={(v) => update({ bigText: v })} />
        <div className="mt-2">
          <SwitchRow
            label="高对比模式"
            desc="提高文字与背景的对比度"
            checked={settings.highContrast}
            onChange={(v) => update({ highContrast: v })}
          />
        </div>
      </SectionCard>

      <SectionCard title="提醒">
        <SwitchRow
          label="服药提醒"
          checked={settings.medicationReminder}
          onChange={(v) => update({ medicationReminder: v })}
        />
        <SwitchRow
          label="测量提醒"
          desc="打开 App 时提醒，不做后台推送"
          checked={settings.measurementReminder}
          onChange={(v) => update({ measurementReminder: v })}
        />
      </SectionCard>

      <SectionCard title="安全">
        <Link
          to="/me/profile"
          className="flex min-h-[64px] items-center gap-2 border-b border-line py-2"
        >
          <span className="t-body flex-1">紧急联系人管理</span>
          <ChevronRightIcon size={22} className="text-ink-soft" />
        </Link>
        <button
          type="button"
          onClick={() => setPwdOpen(true)}
          className="flex min-h-[64px] w-full items-center gap-2 py-2 text-left"
        >
          <span className="t-body flex-1">修改密码</span>
          <ChevronRightIcon size={22} className="text-ink-soft" />
        </button>
      </SectionCard>

      <SectionCard title="关于">
        <Link
          to="/me/settings/legal/disclaimer"
          className="flex min-h-[64px] items-center gap-2 border-b border-line py-2"
        >
          <span className="t-body flex-1">免责声明</span>
          <ChevronRightIcon size={22} className="text-ink-soft" />
        </Link>
        <Link
          to="/me/settings/legal/privacy"
          className="flex min-h-[64px] items-center gap-2 border-b border-line py-2"
        >
          <span className="t-body flex-1">隐私政策</span>
          <ChevronRightIcon size={22} className="text-ink-soft" />
        </Link>
        <a
          href="mailto:feedback@example.com?subject=%E5%BF%83%E8%B4%B4%E5%B0%8F%E6%8A%A4%E5%A3%AB%E6%84%8F%E8%A7%81%E5%8F%8D%E9%A6%88"
          className="flex min-h-[64px] items-center gap-2 border-b border-line py-2"
        >
          <span className="t-body flex-1">意见反馈</span>
          <ChevronRightIcon size={22} className="text-ink-soft" />
        </a>
        <div className="flex min-h-[64px] items-center py-2">
          <span className="t-body flex-1">版本号</span>
          <span className="t-micro text-ink-soft">{APP_VERSION}</span>
        </div>
      </SectionCard>

      <ChangePasswordDialog open={pwdOpen} onClose={() => setPwdOpen(false)} />
    </div>
  )
}
