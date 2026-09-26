import { formatDate } from '../../../lib/foundryFormat'
import type { StudyCatalog, StudyMaterial, StudyMaterialStatus } from '../../../lib/studyMaterialApi'
import { TemplateCanvas } from './TemplateCanvas'

const STATUS_LABELS: Record<StudyMaterialStatus, string> = {
  configuring: 'Configuring',
  generating: 'Generating',
  draft: 'Draft',
  finalizing: 'Finalizing',
  finalized: 'Finalized',
  failed: 'Failed',
}

const STATUS_PILL: Record<StudyMaterialStatus, string> = {
  configuring: 'as-state--queued',
  generating: 'as-state--running',
  draft: 'as-state--running',
  finalizing: 'as-state--running',
  finalized: 'as-state--completed',
  failed: 'as-state--failed',
}

interface StudyMaterialListProps {
  catalog: StudyCatalog
  materials: StudyMaterial[]
  isLoading: boolean
  onOpen: (materialId: string) => void
  onCreate: () => void
}

export function StudyMaterialList({ catalog, materials, isLoading, onOpen, onCreate }: StudyMaterialListProps) {
  if (isLoading && materials.length === 0) {
    return <div className="as-console__empty">Loading study material…</div>
  }
  if (materials.length === 0) {
    return (
      <div className="as-console__empty dsn-empty">
        <p>No study material yet. Pick a title, theme, and template to start.</p>
        <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onCreate}>
          Create study material
        </button>
      </div>
    )
  }

  return (
    <div className="as-console__sources">
      {materials.map((material) => {
        const template = catalog.templates.find((item) => item.id === material.template_id)
        const theme = catalog.themes.find((item) => item.id === material.theme_id)
        return (
          <article className="as-console__panel as-console__artifact-card dsn-card" key={material.id}>
            {template && theme ? (
              <div className="dsn-card__preview">
                <TemplateCanvas
                  template={template}
                  theme={theme}
                  title={material.title}
                  options={material.options}
                  mini
                />
              </div>
            ) : null}
            <h3 className="dsn-card__title">{material.title}</h3>
            <p className="as-console__card-desc">
              {template?.name ?? material.template_id} · {theme?.name ?? material.theme_id} ·{' '}
              {material.component_count} {material.component_count === 1 ? 'component' : 'components'}
            </p>
            <div className="as-console__card-fill" aria-hidden="true" />
            <div className="as-console__artifact-foot">
              <span className="seg">
                <span className={`as-console__statepill ${STATUS_PILL[material.status]}`}>
                  {STATUS_LABELS[material.status]}
                </span>
              </span>
              <span className="seg">{formatDate(material.updated_at)}</span>
              <span className="seg">
                <button
                  type="button"
                  className="as-console__statepill as-state--download"
                  onClick={() => onOpen(material.id)}
                >
                  Open
                </button>
              </span>
            </div>
          </article>
        )
      })}
    </div>
  )
}
