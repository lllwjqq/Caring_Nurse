import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

interface ToastContextValue {
  showToast: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const showToast = useCallback((text: string) => {
    setMessage(text)
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => setMessage(null), 2000)
  }, [])

  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
    },
    [],
  )

  const value = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      {message && (
        <div
          aria-live="polite"
          className="fixed left-1/2 z-[90] -translate-x-1/2 animate-toast-in rounded-full bg-ink px-5 py-3 text-white"
          style={{
            bottom: 'calc(var(--tabbar-h) + var(--safe-bottom) + 16px)',
            maxWidth: 'min(86vw, 420px)',
          }}
        >
          <span className="t-body">{message}</span>
        </div>
      )}
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
