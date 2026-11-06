import { useParams } from 'react-router-dom'
import { PlayIcon } from '../../components/icons'
import { LEGAL_DOCS } from '../../constants/legal'
import { useVoice } from '../../context/VoiceContext'

/** 免责声明 / 隐私政策全屏子页（规格 §6.5.4）。 */
export default function LegalPage() {
  const { doc } = useParams()
  const key = doc === 'privacy' ? 'privacy' : 'disclaimer'
  const data = LEGAL_DOCS[key]
  const voice = useVoice()

  return (
    <div className="space-y-4 px-5 py-5">
      <h1 className="t-h1">{data.title}</h1>

      <button
        type="button"
        onClick={() => void voice.speak(data.body.join('。'))}
        className="btn btn-ghost"
        style={{ minHeight: 48 }}
      >
        <PlayIcon size={20} /> 听一遍
      </button>

      {data.body.map((p, i) => (
        <p key={i} className="t-body text-ink">
          {p}
        </p>
      ))}

      <p className="t-micro text-ink-soft">版本 1.0.0</p>
    </div>
  )
}
