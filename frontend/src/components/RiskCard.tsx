import { useState } from 'react'

interface RiskCardProps {
  level: string
  copy: string
  updatedAt?: string
}

interface RiskMeta {
  label: string
  bg: string
  text: string
  why: string
}

const RISK_META: Record<string, RiskMeta> = {
  green: {
    label: '稳定',
    bg: 'bg-level-green',
    text: 'text-white',
    why: '暂未发现需要特别处理的异常指标，保持规律监测即可。',
  },
  yellow: {
    label: '关注',
    bg: 'bg-level-yellow',
    text: 'text-level-yellow-ink',
    why: '部分指标接近上限，建议调整作息与饮食并继续监测。',
  },
  orange: {
    label: '警告',
    bg: 'bg-level-orange',
    text: 'text-white',
    why: '存在明显异常指标，建议尽快联系医生评估。',
  },
  red: {
    label: '危险',
    bg: 'bg-level-red',
    text: 'text-white',
    why: '存在严重异常，请立即就医或拨打 120。',
  },
}

/** 风险等级卡（规格 §6.2）。 */
export default function RiskCard({ level, copy, updatedAt }: RiskCardProps) {
  const [expanded, setExpanded] = useState(false)
  const meta = RISK_META[level] ?? RISK_META.green

  return (
    <button
      type="button"
      onClick={() => setExpanded((v) => !v)}
      aria-expanded={expanded}
      className={`w-full rounded-card p-5 text-left shadow-card ${meta.bg} ${meta.text}`}
    >
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: 'currentColor' }} aria-hidden="true" />
        <span className="t-h1">{meta.label}</span>
      </div>
      <p className="t-body mt-1">{copy}</p>
      <p className="t-cap mt-1 opacity-90">{updatedAt ?? '刚更新'}</p>
      {expanded && <p className="t-cap mt-2 opacity-90">{meta.why}</p>}
    </button>
  )
}
