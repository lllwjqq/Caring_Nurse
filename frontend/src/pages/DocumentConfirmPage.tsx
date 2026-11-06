import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { featureApi } from '../api/client'
import DocumentConfirmForm from '../components/DocumentConfirmForm'
import DocumentModulesView from '../components/DocumentModulesView'
import SectionCard from '../components/SectionCard'
import { CheckIcon } from '../components/icons'
import { DOC_STATUS_LABELS, DOC_TYPE_LABELS, type MedicalDocumentItem } from '../lib/types'

interface DocAction {
  type: string
  summary: string
}

/** OCR 确认子页（规格 §6.3 / §7.6）。 */
export default function DocumentConfirmPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<MedicalDocumentItem | null>(null)
  const [actions, setActions] = useState<DocAction[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(false)
    try {
      const { data } = await featureApi.getDocument(Number(id))
      setDoc(data as MedicalDocumentItem)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) {
    return (
      <div className="px-5 py-8 text-center">
        <span className="t-body text-ink-soft">正在加载识别结果…</span>
      </div>
    )
  }

  if (error || !doc) {
    return (
      <div className="px-5 py-5">
        <div className="rounded-card bg-white p-5 text-center shadow-card">
          <p className="t-body text-ink-soft">单据不存在或加载失败</p>
          <button
            type="button"
            onClick={() => navigate('/record')}
            className="btn btn-primary mt-4"
            style={{ minHeight: 48 }}
          >
            返回录入
          </button>
        </div>
      </div>
    )
  }

  const readOnly = doc.status === 'confirmed' || doc.status === 'discarded'
  const metrics = doc.parsed_data?.metrics ?? []
  const medications = doc.parsed_data?.medications ?? []

  return (
    <div className="space-y-5 px-5 py-5">
      {actions && (
        <SectionCard title="已执行的操作">
          <ul className="space-y-2">
            {actions.map((a, i) => (
              <li key={i} className="t-body flex items-start gap-2 text-level-green">
                <CheckIcon size={20} />
                {a.summary}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => navigate('/record')}
            className="btn btn-primary mt-4 w-full"
            style={{ minHeight: 56 }}
          >
            返回录入
          </button>
        </SectionCard>
      )}

      {doc.ocr_text && (
        <SectionCard title="OCR 识别原文">
          <details>
            <summary className="t-cap cursor-pointer text-primary-deep">
              展开 / 收起原文
            </summary>
            <p className="t-body mt-2 whitespace-pre-wrap break-words text-ink">
              {doc.ocr_text}
            </p>
          </details>
        </SectionCard>
      )}

      {doc.parsed_data?.modules && (
        <DocumentModulesView modules={doc.parsed_data.modules} />
      )}

      {['other', 'prescription', 'drug_insert'].includes(doc.doc_type) && (
        <SectionCard title="药品匹配（仅文字匹配）">
          {(doc.parsed_data?.drug_matches?.length ?? 0) > 0 ? (
            <ul className="space-y-1">
              {doc.parsed_data?.drug_matches?.map((drug, index) => (
                <li key={index} className="t-body text-ink">
                  {drug.name}
                  {drug.spec ? `（${drug.spec}）` : ''}
                </li>
              ))}
            </ul>
          ) : (
            <p className="t-body text-ink-soft">
              未在药品库匹配到药品。暂不支持拍照/条码识药，请手动输入药名、剂量和用法。
            </p>
          )}
        </SectionCard>
      )}

      {readOnly ? (
        <SectionCard title="单据详情">
          <p className="t-body">{DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}</p>
          <p className="t-cap mt-1 text-ink-soft">
            状态：{DOC_STATUS_LABELS[doc.status] ?? doc.status}
          </p>

          {metrics.length > 0 && (
            <ul className="mt-3 space-y-1">
              {metrics.map((m, i) => (
                <li key={i} className="t-body">
                  {m.name}{' '}
                  {m.record_type === 'blood_pressure'
                    ? `${m.systolic ?? ''}/${m.diastolic ?? ''}`
                    : m.value}
                  {m.unit}
                </li>
              ))}
            </ul>
          )}

          {medications.length > 0 && (
            <ul className="mt-3 space-y-1">
              {medications.map((m, i) => (
                <li key={i} className="t-body">
                  {m.generic_name || m.name} {m.dose ?? ''}
                  {m.dose_unit ?? ''}
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            onClick={() => navigate('/record')}
            className="btn btn-ghost mt-4 w-full"
            style={{ minHeight: 48 }}
          >
            返回录入
          </button>
        </SectionCard>
      ) : (
        <DocumentConfirmForm
          document={doc}
          onConfirmed={(list) => {
            setActions(list)
            void load()
          }}
          onRejected={() => navigate('/record')}
        />
      )}
    </div>
  )
}
