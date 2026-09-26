import { CheckCircle2, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { formatDateTime } from '../../../lib/foundryFormat'
import {
  COMPONENT_TYPE_LABELS,
  getDraftHtml,
  type StudyMaterial,
  type StudyTemplate,
  type StudyTheme,
} from '../../../lib/studyMaterialApi'
import { ErrorBanner } from '../ErrorBanner'
import { ForgeLoader } from './ForgeLoader'
import { RunSteps } from './RunSteps'

const CSS_PX_PER_IN = 96

interface DraftViewProps {
  material: StudyMaterial
  template: StudyTemplate
  theme: StudyTheme
  isBusy: boolean
  onBack: () => void
  onEdit: () => void
  onFinalize: () => void
  onReopen: () => void
  onDownload: () => void
}

function usePageScale(pageWidthPx: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.6)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => {
      setScale(Math.min(1, entry.contentRect.width / pageWidthPx))
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [pageWidthPx])
  return { ref, scale }
}

export function DraftView({
  material,
  template,
  theme,
  isBusy,
  onBack,
  onEdit,
  onFinalize,
  onReopen,
  onDownload,
}: DraftViewProps) {
  const [html, setHtml] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const pageWidthPx = template.page.width_in * CSS_PX_PER_IN
  const pageHeightPx = template.page.height_in * CSS_PX_PER_IN
  const { ref, scale } = usePageScale(pageWidthPx)
  const finalized = material.status === 'finalized'
  const finalizing = material.status === 'finalizing'
  const issues = material.validation.issues ?? []
  const checkedAtFinalize = material.validation.stage === 'finalize'

  useEffect(() => {
    let cancelled = false
    getDraftHtml(material.id)
      .then((next) => {
        if (!cancelled) setHtml(next)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof Error ? caught.message : 'Could not load the draft.')
      })
    return () => {
      cancelled = true
    }
  }, [material.id, material.updated_at])

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">
            Study Material · {finalized ? 'Final' : 'Step 4 of 4'}
          </div>
          <h2>{material.title}</h2>
        </div>
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onBack}>
            All materials
          </button>
          {finalized ? (
            <>
              <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onReopen} disabled={isBusy}>
                Return to editing
              </button>
              <button type="button" className="as-console__cta" onClick={onDownload}>
                Export PDF
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="as-console__cta as-console__cta--ghost"
                onClick={onEdit}
                disabled={finalizing || isBusy}
              >
                Edit components
              </button>
              <button
                type="button"
                className="as-console__cta"
                onClick={onFinalize}
                disabled={finalizing || isBusy}
              >
                {finalizing ? 'Finalizing…' : 'Finalize'}
              </button>
            </>
          )}
        </div>
      </header>

      <div className="as-console__scroll">
        {loadError ? <ErrorBanner message={loadError} /> : null}
        {material.error ? <ErrorBanner message={material.error} /> : null}
        <div className="dsn-workbench dsn-workbench--draft">
          <section className="dsn-canvas-panel" aria-label="Draft preview">
            <div ref={ref} className="dsn-preview" style={{ height: pageHeightPx * scale }}>
              {html ? (
                <iframe
                  title={`${material.title} preview`}
                  className="dsn-preview__frame"
                  sandbox=""
                  srcDoc={html}
                  style={{
                    width: pageWidthPx,
                    height: pageHeightPx,
                    transform: `scale(${scale})`,
                  }}
                />
              ) : (
                <ForgeLoader label="Loading the draft" size="sm" />
              )}
            </div>
          </section>

          <aside className="dsn-side">
            {finalizing ? (
              <section className="as-console__panel dsn-side__panel">
                <ForgeLoader label="Validating the page and printing the PDF" size="sm" />
                <RunSteps runId={material.production_run_id} />
              </section>
            ) : null}

            {finalized ? (
              <div className="dsn-alert dsn-alert--success" role="status">
                <CheckCircle2 size={18} aria-hidden="true" />
                <div>
                  <strong>Finalized {material.finalized_at ? formatDateTime(material.finalized_at) : ''}.</strong>{' '}
                  The PDF is in the Academy Library under Study Material.
                </div>
              </div>
            ) : issues.length ? (
              <div className="dsn-alert dsn-alert--warning" role="alert">
                <TriangleAlert size={18} aria-hidden="true" />
                <div>
                  <strong>
                    {checkedAtFinalize ? 'Finalize blocked' : 'Review before finalizing'}: {issues.length}{' '}
                    {issues.length === 1 ? 'issue' : 'issues'}
                  </strong>
                  <ul className="dsn-issues">
                    {issues.map((issue, index) => (
                      <li key={`${issue.code}-${index}`}>{issue.message}</li>
                    ))}
                  </ul>
                  <p className="dsn-hint">
                    Shorten instructions or move a component to another section, then generate again.
                  </p>
                </div>
              </div>
            ) : !finalizing ? (
              <div className="dsn-alert dsn-alert--success" role="status">
                <CheckCircle2 size={18} aria-hidden="true" />
                <div>
                  <strong>Fits the page.</strong> Finalize checks the page again, prints the PDF, and
                  adds it to the Library.
                </div>
              </div>
            ) : null}

            <section className="as-console__panel">
              <div className="as-console__panel-head">
                <h3>Artifact</h3>
              </div>
              <dl className="dsn-facts">
                <dt>Template</dt>
                <dd>{template.name}</dd>
                <dt>Theme</dt>
                <dd>{theme.name}</dd>
                <dt>Page</dt>
                <dd>
                  {template.page.size} {template.page.width_in} × {template.page.height_in} in
                </dd>
                <dt>Logo</dt>
                <dd>{material.options.logo_locked ? 'Locked' : 'None'}</dd>
              </dl>
            </section>

            <section className="as-console__panel">
              <div className="as-console__panel-head">
                <h3>Components</h3>
                <span className="as-count">{material.components.length}</span>
              </div>
              <ul className="dsn-versions">
                {material.components.map((component) => {
                  const section = template.sections.find((item) => item.id === component.section_id)
                  const version = component.active_version
                  return (
                    <li key={component.id}>
                      <span className="dsn-versions__name">
                        {COMPONENT_TYPE_LABELS[component.component_type]} · {section?.label ?? component.section_id}
                      </span>
                      <span className="dsn-versions__meta">
                        {version ? `v${version.version} · ${version.model ?? 'model'}` : 'Not generated'}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </section>
          </aside>
        </div>
      </div>
    </>
  )
}
