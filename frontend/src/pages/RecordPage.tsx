import { useState } from 'react'
import DocumentUploader from '../components/DocumentUploader'
import MedicationForm from '../components/MedicationForm'
import MetricForm from '../components/MetricForm'
import SectionCard from '../components/SectionCard'
import { CameraIcon, ChevronRightIcon, PillIcon, PlusCircleIcon } from '../components/icons'

type Mode = 'metric' | 'medication' | 'document' | null

const ENTRIES = [
  { key: 'metric' as const, label: '记一项指标', Icon: PlusCircleIcon },
  { key: 'medication' as const, label: '添加用药', Icon: PillIcon },
  { key: 'document' as const, label: '上传报告', Icon: CameraIcon },
]

/** 录入页（规格 §6.3）：三入口常驻，表单区按选中展开且不丢已填内容。 */
export default function RecordPage() {
  const [mode, setMode] = useState<Mode>(null)

  return (
    <div className="space-y-4 px-5 py-5">
      {ENTRIES.map(({ key, label, Icon }) => {
        const active = mode === key
        return (
          <button
            key={key}
            type="button"
            onClick={() => setMode(active ? null : key)}
            aria-expanded={active}
            className={`flex w-full items-center gap-3 rounded-card px-5 text-left shadow-card ${
              active ? 'bg-primary/10' : 'bg-white'
            }`}
            style={{ minHeight: 72 }}
          >
            <Icon size={28} className="text-primary-deep" />
            <span className="t-body flex-1">{label}</span>
            <ChevronRightIcon
              size={24}
              className={`text-ink-soft transition-transform ${active ? 'rotate-90' : ''}`}
            />
          </button>
        )
      })}

      {/* 三个表单保持挂载，切换不丢已填内容 */}
      <div className={mode === 'metric' ? '' : 'hidden'}>
        <SectionCard title="记录指标">
          <MetricForm />
        </SectionCard>
      </div>

      <div className={mode === 'medication' ? '' : 'hidden'}>
        <SectionCard title="添加用药">
          <MedicationForm />
        </SectionCard>
      </div>

      <div className={mode === 'document' ? '' : 'hidden'}>
        <SectionCard title="上传报告">
          <DocumentUploader />
        </SectionCard>
      </div>
    </div>
  )
}
