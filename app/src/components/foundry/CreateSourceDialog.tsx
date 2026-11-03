import { useState, type FormEvent } from 'react'
import type { ReferenceSourceRequest } from '../../lib/workspaceApi'
import { ErrorBanner } from './ErrorBanner'
import { FoundryDialog } from './FoundryDialog'

export function CreateSourceDialog({
  open,
  onClose,
  onCreate,
}: {
  open: boolean
  onClose: () => void
  onCreate: (request: ReferenceSourceRequest) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [background, setBackground] = useState('')
  const [documentType, setDocumentType] = useState('')
  const [issuingAuthority, setIssuingAuthority] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName || isCreating) return
    setIsCreating(true)
    setError(null)
    try {
      await onCreate({
        name: trimmedName,
        background: background.trim() || undefined,
        document_type: documentType.trim() || undefined,
        issuing_authority: issuingAuthority.trim() || undefined,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create that source.')
      setIsCreating(false)
    }
  }

  return (
    <FoundryDialog title="Create source" open={open} onClose={isCreating ? () => undefined : onClose}>
      <form className="as-console__dialog-form" onSubmit={(event) => void handleSubmit(event)}>
        {error ? <ErrorBanner message={error} /> : null}
        <label className="as-console__field-label" htmlFor="reference-source-name">
          Name
        </label>
        <input
          id="reference-source-name"
          className="as-wiki__input"
          value={name}
          disabled={isCreating}
          onChange={(event) => setName(event.target.value)}
          required
        />
        <label className="as-console__field-label" htmlFor="reference-source-background">
          Background
        </label>
        <textarea
          id="reference-source-background"
          className="as-wiki__textarea"
          value={background}
          disabled={isCreating}
          rows={4}
          onChange={(event) => setBackground(event.target.value)}
        />
        <label className="as-console__field-label" htmlFor="reference-source-type">
          Document type
        </label>
        <input
          id="reference-source-type"
          className="as-wiki__input"
          value={documentType}
          disabled={isCreating}
          onChange={(event) => setDocumentType(event.target.value)}
        />
        <label className="as-console__field-label" htmlFor="reference-source-authority">
          Issuing authority
        </label>
        <input
          id="reference-source-authority"
          className="as-wiki__input"
          value={issuingAuthority}
          disabled={isCreating}
          onChange={(event) => setIssuingAuthority(event.target.value)}
        />
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={onClose}
            disabled={isCreating}
          >
            Cancel
          </button>
          <button type="submit" className="as-console__cta" disabled={isCreating || !name.trim()}>
            {isCreating ? 'Creating…' : 'Create source'}
          </button>
        </div>
      </form>
    </FoundryDialog>
  )
}
