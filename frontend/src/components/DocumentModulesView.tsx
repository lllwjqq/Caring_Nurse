interface ModuleItem {
  label: string
  items: string[]
}

interface DocumentModulesViewProps {
  modules?: Record<string, ModuleItem>
}

const ORDER = ['what', 'status', 'abnormal', 'medications', 'lifestyle', 'followup', 'risk', 'questions']
const MARKS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']

/** 病历/出院小结 8 模块（IO_SPEC §4），可复用于确认页与解释页。 */
export default function DocumentModulesView({ modules }: DocumentModulesViewProps) {
  if (!modules) return null
  if (!ORDER.some((key) => modules[key])) return null

  return (
    <div className="space-y-3">
      {ORDER.map((key, index) => {
        const module = modules[key]
        if (!module) return null
        return (
          <section key={key} className="rounded-btn bg-white p-4 shadow-card">
            <h3 className="t-h2 text-ink">
              {MARKS[index]} {module.label}
            </h3>
            <ul className="mt-2 space-y-1">
              {module.items.map((item, itemIndex) => (
                <li key={itemIndex} className="t-body text-ink">
                  {item}
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
