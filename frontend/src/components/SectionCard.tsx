import type { ReactNode } from 'react'

interface SectionCardProps {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

/** 通用区块卡片（规格 §5）。 */
export default function SectionCard({ title, action, children, className }: SectionCardProps) {
  return (
    <section className={`rounded-card bg-white p-5 shadow-card ${className ?? ''}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="t-h2">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}
