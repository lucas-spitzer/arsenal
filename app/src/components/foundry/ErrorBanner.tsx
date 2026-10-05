import { Minus } from 'lucide-react'

interface ErrorBannerProps {
  message: string
  onDismiss?: () => void
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  if (!onDismiss) {
    return (
      <div className="as-console__alert">⚠ {message}</div>
    )
  }

  return (
    <div className="as-console__log">
      <p className="as-console__log-body">⚠ {message}</p>
      <button
        type="button"
        className="as-console__log-dismiss"
        aria-label="Dismiss logs"
        onClick={onDismiss}
      >
        <Minus size={14} strokeWidth={2} />
      </button>
    </div>
  )
}
