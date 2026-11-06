import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { featureApi } from '../api/client'
import { useToast } from './Toast'
import { CameraIcon, ChevronRightIcon } from './icons'
import { DOC_STATUS_LABELS, DOC_TYPE_LABELS, type MedicalDocumentItem } from '../lib/types'

/** 报告上传卡 + 历史单据（规格 §6.3）。 */
export default function DocumentUploader({ onUploaded }: { onUploaded?: (doc: MedicalDocumentItem) => void }) {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [documents, setDocuments] = useState<MedicalDocumentItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await featureApi.listDocuments()
      setDocuments(data as MedicalDocumentItem[])
    } catch {
      /* 历史列表失败不影响上传 */
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(false)
    try {
      const { data } = await featureApi.uploadDocument(file)
      const doc = data as MedicalDocumentItem
      onUploaded?.(doc)
      navigate(`/record/document/${doc.id}`)
      void load()
    } catch {
      setError(true)
      showToast('上传失败，请重试')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="space-y-4">
      <label
        className="flex w-full cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed border-line bg-white text-center"
        style={{ minHeight: 120 }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={handleFile}
          className="hidden"
          aria-label="上传报告"
        />
        <CameraIcon size={36} className="text-primary-deep" />
        <span className="t-body mt-2">{uploading ? '正在识别…' : '拍照或选择文件'}</span>
        <span className="t-cap mt-1 text-ink-soft">支持图片与 PDF</span>
      </label>

      {error && (
        <div className="rounded-card border-l-4 border-level-red bg-level-red/10 p-4">
          <p className="t-body text-level-red">上传失败，请重新上传</p>
        </div>
      )}

      {documents.length > 0 && (
        <div>
          <h3 className="t-h2 mb-2">历史单据</h3>
          <div className="space-y-2">
            {documents.map((doc) => (
              <button
                key={doc.id}
                type="button"
                onClick={() => navigate(`/record/document/${doc.id}`)}
                className="flex w-full items-center justify-between rounded-btn bg-white px-4 py-3 shadow-card"
              >
                <span className="min-w-0 text-left">
                  <span className="t-body block truncate">{doc.filename}</span>
                  <span className="t-cap text-ink-soft">
                    {DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type} ·{' '}
                    {DOC_STATUS_LABELS[doc.status] ?? doc.status}
                  </span>
                </span>
                <ChevronRightIcon size={22} className="shrink-0 text-ink-soft" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
