import { useEffect, useState } from 'react'
import { featureApi } from '../api/client'

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Array<Record<string, unknown>>>([])
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')

  const load = () => {
    featureApi.listDocuments().then((res) => setDocuments(res.data))
  }

  useEffect(() => { load() }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setMessage('')
    try {
      await featureApi.uploadDocument(file)
      setMessage('上传成功，报告已解析')
      load()
    } catch {
      setMessage('上传失败')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <h3 className="font-semibold mb-2">上传体检报告</h3>
        <p className="text-sm text-gray-500 mb-4">支持 PDF、图片格式，系统将自动 OCR 解析健康指标</p>
        <label className="block w-full border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-primary">
          <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={handleUpload} className="hidden" />
          <div className="text-3xl mb-2">📤</div>
          <p className="text-sm text-gray-500">{uploading ? '上传解析中...' : '点击选择文件'}</p>
        </label>
        {message && <p className="text-sm text-primary mt-2">{message}</p>}
      </div>

      {documents.map((doc) => {
        const parsed = doc.parsed_data as { metrics?: Array<Record<string, unknown>> } | null
        return (
          <div key={doc.id as number} className="bg-white rounded-2xl p-4 shadow-sm">
            <div className="flex justify-between items-center">
              <h3 className="font-medium">{doc.filename as string}</h3>
              <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                {doc.status as string}
              </span>
            </div>
            {doc.ocr_text ? (
              <pre className="text-xs text-gray-600 mt-3 bg-gray-50 p-3 rounded-lg whitespace-pre-wrap max-h-40 overflow-y-auto">
                {String(doc.ocr_text)}
              </pre>
            ) : null}
            {parsed?.metrics && parsed.metrics.length > 0 && (
              <div className="mt-3">
                <h4 className="text-sm font-medium text-gray-600 mb-2">提取指标</h4>
                <div className="grid grid-cols-2 gap-2">
                  {parsed.metrics.map((m, i) => (
                    <div key={i} className="bg-blue-50 rounded-lg p-2 text-sm">
                      <span className="text-gray-500">{m.type as string}: </span>
                      <span className="font-medium">
                        {m.value !== undefined ? `${m.value}` : `${m.systolic}/${m.diastolic}`}
                        {m.unit as string}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
