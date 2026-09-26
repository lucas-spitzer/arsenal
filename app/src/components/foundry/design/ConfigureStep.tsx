import { Lock, Plus } from 'lucide-react'
import { useState } from 'react'
import {
  catalogAssetUrl,
  COMPONENT_TYPE_LABELS,
  createComponent,
  updateStudyMaterial,
  type ComponentType,
  type FlexibleSection,
  type StrictSection,
  type StudyCatalog,
  type StudyComponent,
  type StudyMaterial,
  type StudyMaterialOptions,
  type StudyTemplate,
  type StudyTheme,
} from '../../../lib/studyMaterialApi'
import { ErrorBanner } from '../ErrorBanner'
import { ComponentEditor } from './ComponentEditor'
import { COMPONENT_ICONS } from './componentIcons'
import { TemplateCanvas } from './TemplateCanvas'

interface ConfigureStepProps {
  material: StudyMaterial
  catalog: StudyCatalog
  template: StudyTemplate
  theme: StudyTheme
  isStarting: boolean
  onMaterialChange: (material: StudyMaterial) => void
  onGenerate: () => void
  onBack: () => void
  onDelete: () => void
}

function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

export function ConfigureStep({
  material,
  catalog,
  template,
  theme,
  isStarting,
  onMaterialChange,
  onGenerate,
  onBack,
  onDelete,
}: ConfigureStepProps) {
  const firstFlexible = template.sections.find((section) => section.kind === 'flexible')
  const [selectedId, setSelectedId] = useState<string | null>(firstFlexible?.id ?? null)
  const [error, setError] = useState<string | null>(null)
  const selected = template.sections.find((section) => section.id === selectedId) ?? null
  const components = material.components

  const setComponents = (next: StudyComponent[]) => {
    onMaterialChange({ ...material, components: next, component_count: next.length })
  }

  const saveMaterial = async (payload: { title?: string; options?: StudyMaterialOptions }) => {
    setError(null)
    try {
      onMaterialChange({ ...(await updateStudyMaterial(material.id, payload)) })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save.')
    }
  }

  const addComponent = async (section: FlexibleSection, componentType: ComponentType) => {
    setError(null)
    try {
      const created = await createComponent(material.id, {
        section_id: section.id,
        component_type: componentType,
      })
      setComponents([...components, created])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not add the component.')
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Study Material · Step 2 of 4</div>
          <h2>{material.title}</h2>
        </div>
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onBack}>
            All materials
          </button>
          <button type="button" className="as-console__cta as-console__cta--ghost dsn-cta--danger" onClick={onDelete}>
            Delete
          </button>
          <button
            type="button"
            className="as-console__cta"
            disabled={components.length === 0 || isStarting}
            onClick={onGenerate}
          >
            {isStarting ? 'Starting…' : 'Generate'}
          </button>
        </div>
      </header>

      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} onDismiss={() => setError(null)} /> : null}
        {material.status === 'failed' && material.error ? (
          <div className="dsn-alert dsn-alert--error" role="alert">
            <strong>Last run failed.</strong> {material.error} Components that finished are kept;
            Generate retries the rest.
          </div>
        ) : null}

        <div className="dsn-workbench">
          <section className="dsn-canvas-panel" aria-label="Template">
            <p className="dsn-hint">
              {template.name} · {theme.name}. Select a section to configure it.
            </p>
            <TemplateCanvas
              template={template}
              theme={theme}
              title={material.title}
              options={material.options}
              components={components}
              selectedSectionId={selectedId}
              onSelect={setSelectedId}
            />
          </section>

          <section className="as-console__panel dsn-inspector" aria-live="polite">
            {selected === null ? (
              <p className="dsn-hint">Select a section on the template.</p>
            ) : selected.kind === 'strict' ? (
              <StrictInspector
                key={selected.id}
                section={selected}
                material={material}
                theme={theme}
                template={template}
                onSave={(payload) => void saveMaterial(payload)}
              />
            ) : (
              <FlexibleInspector
                key={selected.id}
                section={selected}
                material={material}
                catalog={catalog}
                components={components.filter((item) => item.section_id === selected.id)}
                onAdd={(componentType) => void addComponent(selected, componentType)}
                onChange={(updated) =>
                  setComponents(components.map((item) => (item.id === updated.id ? updated : item)))
                }
                onDelete={(componentId) => setComponents(components.filter((item) => item.id !== componentId))}
                onSaveNotes={(notes) =>
                  void saveMaterial({
                    options: {
                      ...material.options,
                      section_notes: { ...material.options.section_notes, [selected.id]: notes },
                    },
                  })
                }
                onError={setError}
              />
            )}
          </section>
        </div>
      </div>
    </>
  )
}

function StrictInspector({
  section,
  material,
  theme,
  template,
  onSave,
}: {
  section: StrictSection
  material: StudyMaterial
  theme: StudyTheme
  template: StudyTemplate
  onSave: (payload: { title?: string; options?: StudyMaterialOptions }) => void
}) {
  const [title, setTitle] = useState(material.title)
  const [footer, setFooter] = useState(material.options.footer_text)
  const lightLogos = theme.logos.filter((logo) => logo.variant === 'light')
  const maxWords = section.max_words ?? 20
  const footerWords = wordCount(footer)

  return (
    <div className="dsn-inspector__body">
      <div className="as-console__panel-head dsn-inspector__head">
        <Lock size={14} aria-hidden="true" />
        <h3>{section.label}</h3>
        <span className="as-console__ws-badge">Locked</span>
      </div>

      {section.content === 'title' ? (
        <>
          <p className="dsn-hint">Prints the material title only. Generated content never goes here.</p>
          <label className="as-console__field-label dsn-label-sm" htmlFor="dsn-inspector-title">
            Title
          </label>
          <input
            id="dsn-inspector-title"
            className="as-wiki__input"
            value={title}
            maxLength={140}
            onChange={(event) => setTitle(event.target.value)}
            onBlur={() => {
              if (title.trim() && title.trim() !== material.title) onSave({ title: title.trim() })
            }}
          />
        </>
      ) : null}

      {section.content === 'logo' ? (
        lightLogos.length ? (
          <>
            <label className="dsn-check">
              <input
                type="checkbox"
                checked={material.options.logo_locked}
                onChange={(event) =>
                  onSave({
                    options: {
                      ...material.options,
                      logo_locked: event.target.checked,
                      logo_id: event.target.checked
                        ? material.options.logo_id ?? theme.default_logo_id
                        : null,
                    },
                  })
                }
              />
              <span>Lock a theme logo in this band</span>
            </label>
            {material.options.logo_locked ? (
              <div className="dsn-logo-options" role="radiogroup" aria-label="Logo">
                {lightLogos.map((logo) => (
                  <label
                    key={logo.id}
                    className={`dsn-logo-option${material.options.logo_id === logo.id ? ' is-selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="dsn-inspector-logo"
                      className="sr-only"
                      checked={material.options.logo_id === logo.id}
                      onChange={() => onSave({ options: { ...material.options, logo_id: logo.id } })}
                    />
                    <img src={catalogAssetUrl(logo.asset)} alt="" />
                    <span>{logo.label}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="dsn-hint">The band stays empty.</p>
            )}
          </>
        ) : (
          <p className="dsn-hint">{theme.name} has no logos, so this band stays empty.</p>
        )
      ) : null}

      {section.content === 'footer' ? (
        <>
          <label className="as-console__field-label dsn-label-sm" htmlFor="dsn-inspector-footer">
            Footer text (optional)
          </label>
          <input
            id="dsn-inspector-footer"
            className="as-wiki__input"
            value={footer}
            onChange={(event) => setFooter(event.target.value)}
            onBlur={() => {
              if (footer.trim() !== material.options.footer_text && footerWords <= maxWords) {
                onSave({ options: { ...material.options, footer_text: footer.trim() } })
              }
            }}
            aria-describedby="dsn-footer-count"
            aria-invalid={footerWords > maxWords}
          />
          <p id="dsn-footer-count" className={`dsn-hint${footerWords > maxWords ? ' is-error' : ''}`}>
            {footerWords} / {maxWords} words
          </p>
          {theme.disclaimer && template.disclaimer === 'footer' ? (
            <div className="dsn-alert dsn-alert--info">
              <strong>Always printed:</strong> {theme.disclaimer}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

function FlexibleInspector({
  section,
  material,
  catalog,
  components,
  onAdd,
  onChange,
  onDelete,
  onSaveNotes,
  onError,
}: {
  section: FlexibleSection
  material: StudyMaterial
  catalog: StudyCatalog
  components: StudyComponent[]
  onAdd: (componentType: ComponentType) => void
  onChange: (component: StudyComponent) => void
  onDelete: (componentId: string) => void
  onSaveNotes: (notes: string) => void
  onError: (message: string) => void
}) {
  const [notes, setNotes] = useState(material.options.section_notes[section.id] ?? '')
  const full = components.length >= section.max_components
  const [width, height] = section.size_in
  const counters: Record<ComponentType, number> = { text: 0, diagram: 0, image: 0 }

  return (
    <div className="dsn-inspector__body">
      <div className="as-console__panel-head dsn-inspector__head">
        <h3>{section.label}</h3>
        <span className="as-count">
          {components.length} / {section.max_components}
        </span>
      </div>
      <p className="dsn-hint">
        {width} × {height} in. The orchestrator sets order, size, and spacing inside this section only.
      </p>

      <div className="dsn-add-row" role="group" aria-label="Add component">
        {section.allowed_types.map((componentType) => {
          const Icon = COMPONENT_ICONS[componentType]
          return (
            <button
              key={componentType}
              type="button"
              className="as-console__cta as-console__cta--ghost dsn-cta--sm"
              disabled={full}
              onClick={() => onAdd(componentType)}
            >
              <Plus size={14} aria-hidden="true" />
              <Icon size={14} aria-hidden="true" />
              {COMPONENT_TYPE_LABELS[componentType]}
            </button>
          )
        })}
      </div>
      {full ? <p className="dsn-hint">This section is full.</p> : null}

      {components.map((component) => {
        counters[component.component_type] += 1
        return (
          <ComponentEditor
            key={component.id}
            materialId={material.id}
            component={component}
            index={counters[component.component_type]}
            catalog={catalog}
            disabled={false}
            onChange={onChange}
            onDelete={onDelete}
            onError={onError}
          />
        )
      })}

      <label className="as-console__field-label dsn-label-sm" htmlFor={`dsn-notes-${section.id}`}>
        Layout notes (optional)
      </label>
      <textarea
        id={`dsn-notes-${section.id}`}
        className="as-wiki__textarea"
        rows={2}
        maxLength={500}
        value={notes}
        placeholder="Put the diagram first. Keep the takeaways at the bottom."
        onChange={(event) => setNotes(event.target.value)}
        onBlur={() => {
          if (notes.trim() !== (material.options.section_notes[section.id] ?? '')) onSaveNotes(notes.trim())
        }}
      />
    </div>
  )
}
