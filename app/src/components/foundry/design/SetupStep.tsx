import { useState } from 'react'
import { useWorkspace } from '../../../features/workspace/workspaceContext'
import {
  catalogAssetUrl,
  createStudyMaterial,
  type StudyCatalog,
  type StudyMaterial,
  type StudyMaterialOptions,
} from '../../../lib/studyMaterialApi'
import { ErrorBanner } from '../ErrorBanner'
import { TemplateCanvas } from './TemplateCanvas'

interface SetupStepProps {
  catalog: StudyCatalog
  onCancel: () => void
  onCreated: (material: StudyMaterial) => void
}

const SWATCH_KEYS = ['heading', 'accent_dark', 'secondary', 'ink'] as const

export function SetupStep({ catalog, onCancel, onCreated }: SetupStepProps) {
  const { activeWorkspace } = useWorkspace()
  const [title, setTitle] = useState('')
  const [themeId, setThemeId] = useState<string | null>(null)
  const [templateId, setTemplateId] = useState<string | null>(null)
  const [logoLocked, setLogoLocked] = useState(false)
  const [logoId, setLogoId] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const theme = catalog.themes.find((item) => item.id === themeId) ?? null
  const template = catalog.templates.find((item) => item.id === templateId) ?? null
  const lightLogos = theme?.logos.filter((logo) => logo.variant === 'light') ?? []
  const canLockLogo = Boolean(template?.has_logo_section) && lightLogos.length > 0
  const selectedLogoId = logoId ?? theme?.default_logo_id ?? lightLogos[0]?.id ?? null
  const ready = title.trim().length > 0 && theme !== null && template !== null

  const options: StudyMaterialOptions = {
    logo_locked: canLockLogo && logoLocked,
    logo_id: canLockLogo && logoLocked ? selectedLogoId : null,
    footer_text: '',
    section_notes: {},
  }
  const previewTheme = theme ?? catalog.themes[0]

  const selectTheme = (id: string) => {
    setThemeId(id)
    setLogoId(null)
  }

  const handleNext = async () => {
    if (!ready || !activeWorkspace || !theme || !template) return
    setIsSubmitting(true)
    setError(null)
    try {
      const material = await createStudyMaterial(activeWorkspace.id, {
        title: title.trim(),
        theme_id: theme.id,
        template_id: template.id,
        options,
      })
      onCreated(material)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create the study material.')
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Study Material · Step 1 of 4</div>
          <h2>New study material</h2>
        </div>
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="as-console__cta"
            disabled={!ready || isSubmitting}
            onClick={() => void handleNext()}
          >
            {isSubmitting ? 'Creating…' : 'Next'}
          </button>
        </div>
      </header>

      <div className="as-console__scroll dsn-setup">
        {error ? <ErrorBanner message={error} /> : null}

        <section className="dsn-field">
          <label className="as-console__field-label" htmlFor="dsn-title">
            Title
          </label>
          <input
            id="dsn-title"
            className="as-wiki__input dsn-input-title"
            value={title}
            maxLength={140}
            placeholder="Land Navigation Fundamentals"
            onChange={(event) => setTitle(event.target.value)}
          />
        </section>

        <fieldset className="dsn-field">
          <legend className="as-console__field-label">Theme</legend>
          <div className="dsn-choice-grid">
            {catalog.themes.map((item) => {
              const selected = item.id === themeId
              const logos = item.logos.filter((logo) => logo.variant === 'light')
              return (
                <label key={item.id} className={`dsn-choice${selected ? ' is-selected' : ''}`}>
                  <input
                    type="radio"
                    name="dsn-theme"
                    className="sr-only"
                    checked={selected}
                    onChange={() => selectTheme(item.id)}
                  />
                  <span className="dsn-choice__title">{item.name}</span>
                  <span className="dsn-swatches" aria-hidden="true">
                    {SWATCH_KEYS.map((key) => (
                      <span key={key} className="dsn-swatch" style={{ background: item.colors[key] }} />
                    ))}
                  </span>
                  <span className="dsn-choice__desc">{item.description}</span>
                  {logos.length ? (
                    <span className="dsn-choice__logos">
                      {logos.map((logo) => (
                        <img key={logo.id} src={catalogAssetUrl(logo.asset)} alt={logo.label} />
                      ))}
                    </span>
                  ) : null}
                  {item.disclaimer ? (
                    <span className="dsn-choice__meta">Footer disclaimer: “{item.disclaimer}”</span>
                  ) : null}
                </label>
              )
            })}
          </div>
        </fieldset>

        <fieldset className="dsn-field">
          <legend className="as-console__field-label">Template</legend>
          <div className="dsn-choice-grid dsn-choice-grid--templates">
            {catalog.templates.map((item) => {
              const selected = item.id === templateId
              return (
                <label key={item.id} className={`dsn-choice dsn-choice--template${selected ? ' is-selected' : ''}`}>
                  <input
                    type="radio"
                    name="dsn-template"
                    className="sr-only"
                    checked={selected}
                    onChange={() => setTemplateId(item.id)}
                  />
                  <span className="dsn-choice__preview">
                    <TemplateCanvas
                      template={item}
                      theme={previewTheme}
                      title={title || item.name}
                      options={{ ...options, logo_locked: false, logo_id: null }}
                      mini
                    />
                  </span>
                  <span className="dsn-choice__title">{item.name}</span>
                  <span className="dsn-choice__desc">{item.description}</span>
                  <span className="dsn-choice__meta">
                    {item.page.size} {item.page.width_in} × {item.page.height_in} in · {item.orientation}
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>

        {canLockLogo ? (
          <fieldset className="dsn-field">
            <legend className="as-console__field-label">Logo section</legend>
            <label className="dsn-check">
              <input
                type="checkbox"
                checked={logoLocked}
                onChange={(event) => setLogoLocked(event.target.checked)}
              />
              <span>Lock a theme logo in the logo band</span>
            </label>
            <p className="dsn-hint">
              Off: the band stays empty. On: the chosen logo prints in that space and cannot be
              replaced by generated content.
            </p>
            {logoLocked ? (
              <div className="dsn-logo-options" role="radiogroup" aria-label="Logo">
                {lightLogos.map((logo) => (
                  <label
                    key={logo.id}
                    className={`dsn-logo-option${selectedLogoId === logo.id ? ' is-selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="dsn-logo"
                      className="sr-only"
                      checked={selectedLogoId === logo.id}
                      onChange={() => setLogoId(logo.id)}
                    />
                    <img src={catalogAssetUrl(logo.asset)} alt="" />
                    <span>{logo.label}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </fieldset>
        ) : null}
      </div>
    </>
  )
}
