import { useState, type FormEvent } from 'react'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import type { LibraryArtifactKind, LibraryArtifactUploadRequest, Source } from '../../lib/workspaceApi'
import { ErrorBanner } from './ErrorBanner'
import { FoundryDialog } from './FoundryDialog'

const FILE_ACCEPT: Record<LibraryArtifactKind, string> = {
  audiobook: '.mp3,audio/mpeg',
  knowledge: '.json,application/json',
}

export function UploadArtifactsDialog({
  open,
  sources,
  onClose,
  onUpload,
}: {
  open: boolean
  sources: Source[]
  onClose: () => void
  onUpload: (request: LibraryArtifactUploadRequest) => Promise<void>
}) {
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? '')
  const [artifactType, setArtifactType] = useState<LibraryArtifactKind>('audiobook')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const selectedSourceId = sources.some((source) => source.id === sourceId)
    ? sourceId
    : (sources[0]?.id ?? '')

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedSourceId || !title.trim() || !file || isUploading) return
    setIsUploading(true)
    setError(null)
    try {
      await onUpload({
        sourceId: selectedSourceId,
        artifactType,
        title: title.trim(),
        file,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed.')
      setIsUploading(false)
    }
  }

  return (
    <FoundryDialog title="Upload Artifacts" open={open} onClose={isUploading ? () => undefined : onClose}>
      <form className="as-console__dialog-form" onSubmit={(event) => void handleSubmit(event)}>
        {error ? <ErrorBanner message={error} /> : null}
        <label className="as-console__field-label" htmlFor="artifact-source">
          Source
        </label>
        <select
          id="artifact-source"
          className="as-console__select"
          value={selectedSourceId}
          disabled={isUploading || sources.length === 0}
          onChange={(event) => setSourceId(event.target.value)}
        >
          {sources.length === 0 ? <option value="">No sources yet</option> : null}
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {sourceDisplayName(source)}
            </option>
          ))}
        </select>
        <label className="as-console__field-label" htmlFor="artifact-type">
          Artifact
        </label>
        <select
          id="artifact-type"
          className="as-console__select"
          value={artifactType}
          disabled={isUploading}
          onChange={(event) => {
            const next = event.target.value
            if (next !== 'audiobook' && next !== 'knowledge') return
            setArtifactType(next)
            setFile(null)
          }}
        >
          <option value="audiobook">Audiobook</option>
          <option value="knowledge">Knowledge</option>
        </select>
        <label className="as-console__field-label" htmlFor="artifact-title">
          Title
        </label>
        <input
          id="artifact-title"
          className="as-wiki__input"
          value={title}
          disabled={isUploading}
          onChange={(event) => setTitle(event.target.value)}
        />
        <label className="as-console__field-label" htmlFor="artifact-file">
          File
        </label>
        <input
          id="artifact-file"
          key={artifactType}
          className="as-wiki__input"
          type="file"
          accept={FILE_ACCEPT[artifactType]}
          disabled={isUploading}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={onClose}
            disabled={isUploading}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="as-console__cta"
            disabled={isUploading || !selectedSourceId || !title.trim() || !file}
          >
            {isUploading ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </form>
    </FoundryDialog>
  )
}
