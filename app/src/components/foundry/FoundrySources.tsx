import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { formatDate, statusLabel } from '../../lib/foundryFormat'
import { mapSourceDisplay } from '../../lib/foundryMappers'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import { FoundryViewToggle } from './FoundryViewToggle'
import { ErrorBanner } from './ErrorBanner'
import { FoundryLoader } from './FoundryLoader'
import { UploadArtifactsDialog } from './UploadArtifactsDialog'
import type { FoundryView } from './types'

export function FoundrySources() {
  const { sources, structuredSources, isLoading, error, uploadSource, uploadLibraryArtifact } =
    useWorkspaceData()
  const [query, setQuery] = useState('')
  const [view, setView] = useState<FoundryView>('grid')
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [artifactsOpen, setArtifactsOpen] = useState(false)
  const [artifactsKey, setArtifactsKey] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadSources = useMemo(
    () =>
      [...sources, ...structuredSources].sort((left, right) =>
        sourceDisplayName(left).localeCompare(sourceDisplayName(right)),
      ),
    [sources, structuredSources],
  )

  const displaySources = useMemo(
    () =>
      [...sources, ...structuredSources]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map(mapSourceDisplay),
    [sources, structuredSources],
  )

  const filtered = useMemo(() => {
    const q = query.toLowerCase()
    return displaySources.filter(
      (source) =>
        source.title.toLowerCase().includes(q) ||
        source.filename.toLowerCase().includes(q) ||
        (source.bibliographicTitle?.toLowerCase().includes(q) ?? false) ||
        (source.identifier?.toLowerCase().includes(q) ?? false) ||
        (source.documentType?.toLowerCase().includes(q) ?? false) ||
        (source.issuingAuthority?.toLowerCase().includes(q) ?? false),
    )
  }, [displaySources, query])

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setIsUploading(true)
    setUploadError(null)

    try {
      await uploadSource(file)
    } catch (caught) {
      setUploadError(caught instanceof Error ? caught.message : 'Upload failed.')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Knowledge Base</div>
          <h2>Source Intelligence</h2>
        </div>
        <FoundryViewToggle view={view} onChange={setView} />
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={(event) => void handleUpload(event)}
        />
        <button
          className="as-console__cta as-console__cta--ghost"
          disabled={isUploading}
          onClick={() => {
            setArtifactsKey((key) => key + 1)
            setArtifactsOpen(true)
          }}
        >
          ⇪ Upload Artifacts
        </button>
        <button
          className="as-console__cta as-console__cta--ghost"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {isUploading ? 'Uploading…' : '⇪ Upload document'}
        </button>
      </header>
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}
        {uploadError ? <ErrorBanner message={uploadError} /> : null}
        <div className="as-console__searchbar">
          <span style={{ color: '#6f828b' }}>⌕</span>
          <input
            placeholder="Search sources by name, filename, or research title…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span className="as-count">{filtered.length} files</span>
        </div>
        {isLoading && filtered.length === 0 ? (
          <div className="as-console__empty">
            <FoundryLoader label="Loading sources" size="sm" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="as-console__empty">
            No sources yet. Upload a file to ingest it into the knowledge base.
          </div>
        ) : view === 'list' ? (
          <section className="as-console__panel">
            <table className="as-console__table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Format</th>
                  <th>Status</th>
                  <th>Size</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <div className="as-console__listname">
                        <span>
                          <div className="t">{source.title}</div>
                          <div className="s">
                            {[
                              source.bibliographicTitle &&
                              source.bibliographicTitle !== source.title
                                ? source.bibliographicTitle
                                : null,
                              source.identifier,
                              source.issuingAuthority,
                            ]
                              .filter(Boolean)
                              .join(' · ') || source.filename}
                          </div>
                        </span>
                      </div>
                    </td>
                    <td>{source.documentType ?? '—'}</td>
                    <td className="num">{source.mimeLabel}</td>
                    <td>
                      <span className={`as-console__statepill as-state--${source.status}`}>
                        {statusLabel(source.status)}
                      </span>
                    </td>
                    <td className="num">{source.sizeLabel}</td>
                    <td className="num">{formatDate(source.uploadedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : (
          <div className="as-console__sources">
            {filtered.map((source) => (
              <div className="as-console__panel as-console__source-card" key={source.id} style={{ padding: 18 }}>
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--as-grotesk)',
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      color: '#fff',
                    }}
                  >
                    {source.title}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#9fb2bb', marginTop: 6 }}>
                    {source.purpose
                      ? `Purpose: ${source.purpose}`
                      : [source.documentType, source.issuingAuthority].filter(Boolean).join(' · ') ||
                        (!source.isStructuredData && (source.status === 'stored' || source.status === 'processing')
                          ? 'Ingest in progress'
                          : source.filename)}
                  </div>
                </div>
                {source.pages !== null || source.segments !== null || source.confidence !== null ? (
                  <div className="as-console__step-body">
                    <div className="stats" style={{ marginTop: 12 }}>
                      {source.pages !== null ? <span>{source.pages} pages</span> : null}
                      {source.segments !== null ? <span>{source.segments} segments</span> : null}
                      {source.confidence !== null ? (
                        <span>conf {Math.round(source.confidence * 100)}%</span>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                <div className="as-console__card-fill" aria-hidden="true" />
                <div className="as-console__artifact-foot">
                  <span className="seg">{source.sizeLabel}</span>
                  <span className="seg">{source.mimeLabel}</span>
                  <span className="seg">
                    <span className={`as-console__statepill as-state--${source.status}`}>
                      {statusLabel(source.status)}
                    </span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <UploadArtifactsDialog
        key={artifactsKey}
        open={artifactsOpen}
        sources={uploadSources}
        onClose={() => setArtifactsOpen(false)}
        onUpload={async (request) => {
          await uploadLibraryArtifact(request)
          setArtifactsOpen(false)
        }}
      />
    </>
  )
}
