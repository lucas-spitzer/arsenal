import { Check } from 'lucide-react'

/** How long the burst stays up. Keep in step with `ap-burst` in academy.css. */
export const CORRECT_BURST_MS = 1800

export function CorrectBurst({ label, mastery }: { label: string; mastery: boolean }) {
  return (
    <div className={`ap-burst${mastery ? ' ap-burst--mastery' : ''}`} role="status" aria-live="polite">
      <div className="ap-burst__card">
        <span className="ap-burst__mark" aria-hidden="true">
          <Check size={64} strokeWidth={3} />
        </span>
        <span className="ap-burst__title">{mastery ? 'Mastered' : 'Correct'}</span>
        {label ? <span className="ap-burst__points">{label}</span> : null}
      </div>
    </div>
  )
}
