import { useVoice } from '../context/VoiceContext'
import SosButton from './SosButton'
import { ArrowLeftIcon, HeartIcon, VolumeOffIcon, VolumeOnIcon } from './icons'

export type HeaderVariant = 'identity' | 'title' | 'back'

interface PageHeaderProps {
  variant: HeaderVariant
  title?: string
  onBack?: () => void
  onOpenSos?: () => void
}

/**
 * 全局页头（规格 §4.2）：
 * - 问诊：头像 + 名称 + 在线，右静音 + SOS
 * - 其他 tab：页面标题，右静音 + SOS
 * - 子页：返回 + 标题，右仅静音
 */
export default function PageHeader({ variant, title, onBack, onOpenSos }: PageHeaderProps) {
  const { enabled, setEnabled } = useVoice()

  return (
    <header
      id="page-header"
      className="relative z-50 shrink-0 border-b border-line bg-white"
      style={{ paddingTop: 'var(--safe-top)' }}
    >
      <div className="mx-auto flex h-14 max-w-shell items-center gap-2 px-4">
        {variant === 'back' && (
          <button
            type="button"
            onClick={onBack}
            aria-label="返回"
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-ink-soft"
          >
            <ArrowLeftIcon size={26} />
          </button>
        )}

        {variant === 'identity' && (
          <>
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary-deep">
              <HeartIcon size={22} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="t-h2 block truncate leading-tight">贴心小护士</span>
              <span className="t-cap block leading-tight text-ink-soft">
                <span
                  className="mr-1 inline-block h-2 w-2 rounded-full align-middle"
                  style={{ background: 'rgb(var(--c-level-green))' }}
                />
                在线
              </span>
            </span>
          </>
        )}

        {variant === 'title' && (
          <h1 className="t-h2 min-w-0 flex-1 truncate">{title}</h1>
        )}

        {variant === 'back' && (
          <h1 className="t-h2 min-w-0 flex-1 truncate">{title}</h1>
        )}

        <button
          type="button"
          onClick={() => setEnabled(!enabled)}
          aria-label={enabled ? '静音语音播报' : '开启语音播报'}
          aria-pressed={!enabled}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-ink-soft"
        >
          {enabled ? <VolumeOnIcon size={24} /> : <VolumeOffIcon size={24} />}
        </button>

        {variant !== 'back' && onOpenSos && <SosButton onClick={onOpenSos} />}
      </div>
    </header>
  )
}
