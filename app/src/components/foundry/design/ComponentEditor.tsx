import { Paperclip, Trash2, X } from 'lucide-react'
import { useId, useState, type ChangeEvent } from 'react'
import { formatBytes } from '../../../lib/foundryFormat'
import {
  COMPONENT_TYPE_LABELS,
  deleteComponent,
  deleteComponentFile,
  updateComponent,
  uploadComponentFile,
  type ImageProvider,
  type ImageSettings,
  type StudyCatalog,
  type StudyComponent,
} from '../../../lib/studyMaterialApi'
import { COMPONENT_ICONS } from './componentIcons'

const DOCUMENT_ACCEPT = '.pdf,.md,.markdown,.txt,.csv'
const IMAGE_ACCEPT = '.png,.jpg,.jpeg,.webp'

const INSTRUCTION_HINTS: Record<StudyComponent['component_type'], string> = {
  text: 'What should this text cover? Name the structure if it matters: steps, key terms, a comparison table, questions.',
  diagram: 'What relationships should the diagram show? A process, a breakdown, or a cycle.',
  image: 'Describe the illustration. The theme style is added automatically; no text is drawn in images.',
}

const PROVIDER_LABELS: Record<ImageProvider, string> = { openai: 'OpenAI', google: 'Google' }

interface ComponentEditorProps {
  materialId: string
  component: StudyComponent
  index: number
  catalog: StudyCatalog
  disabled: boolean
  onChange: (component: StudyComponent) => void
  onDelete: (componentId: string) => void
  onError: (message: string) => void
}

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

export function ComponentEditor({
  materialId,
  component,
  index,
  catalog,
  disabled,
  onChange,
  onDelete,
  onError,
}: ComponentEditorProps) {
  const baseId = useId()
  const [instructions, setInstructions] = useState(component.instructions)
  const [busy, setBusy] = useState(false)
  const Icon = COMPONENT_ICONS[component.component_type]
  const isImage = component.component_type === 'image'
  const version = component.active_version
  const fileLimit = catalog.limits.max_files_per_component

  const run = async (task: () => Promise<void>, fallback: string) => {
    setBusy(true)
    try {
      await task()
    } catch (caught) {
      onError(errorMessage(caught, fallback))
    } finally {
      setBusy(false)
    }
  }

  const saveInstructions = () => {
    if (instructions.trim() === component.instructions) return
    void run(async () => {
      onChange(await updateComponent(materialId, component.id, { instructions }))
    }, 'Could not save instructions.')
  }

  const saveSettings = (patch: Partial<ImageSettings>) => {
    const next: Partial<ImageSettings> = { ...component.settings, ...patch }
    if (patch.provider && patch.provider !== component.settings.provider) {
      next.model = catalog.image.default_models[patch.provider]
    }
    void run(async () => {
      onChange(await updateComponent(materialId, component.id, { settings: next }))
    }, 'Could not save image settings.')
  }

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    void run(async () => {
      onChange(await uploadComponentFile(materialId, component.id, file))
    }, 'Upload failed.')
  }

  const removeFile = (fileId: string) => {
    void run(async () => {
      onChange(await deleteComponentFile(materialId, component.id, fileId))
    }, 'Could not remove the file.')
  }

  const remove = () => {
    if (!window.confirm(`Delete ${COMPONENT_TYPE_LABELS[component.component_type]} ${index}?`)) return
    void run(async () => {
      await deleteComponent(materialId, component.id)
      onDelete(component.id)
    }, 'Could not delete the component.')
  }

  const provider: ImageProvider = component.settings.provider ?? catalog.image.default_provider
  const locked = disabled || busy

  return (
    <article className="dsn-component">
      <header className="dsn-component__head">
        <Icon size={16} aria-hidden="true" />
        <h4 className="dsn-component__title">
          {COMPONENT_TYPE_LABELS[component.component_type]} {index}
        </h4>
        <span className={`dsn-component__status${version ? ' is-generated' : ''}`}>
          {version ? `Generated · v${version.version}` : 'Generates on next run'}
        </span>
        <button
          type="button"
          className="dsn-icon-btn dsn-icon-btn--danger"
          onClick={remove}
          disabled={locked}
          aria-label={`Delete ${COMPONENT_TYPE_LABELS[component.component_type]} ${index}`}
        >
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </header>

      <label className="as-console__field-label dsn-label-sm" htmlFor={`${baseId}-instructions`}>
        Instructions
      </label>
      <textarea
        id={`${baseId}-instructions`}
        className="as-wiki__textarea"
        rows={4}
        value={instructions}
        placeholder={INSTRUCTION_HINTS[component.component_type]}
        disabled={disabled}
        onChange={(event) => setInstructions(event.target.value)}
        onBlur={saveInstructions}
      />

      <div className="dsn-files">
        <div className="dsn-files__head">
          <span className="as-console__field-label dsn-label-sm">
            {isImage ? 'Reference image and files' : 'Files'}
          </span>
          <label className={`as-console__cta as-console__cta--ghost dsn-cta--sm${locked || component.files.length >= fileLimit ? ' is-disabled' : ''}`}>
            <Paperclip size={14} aria-hidden="true" />
            Attach
            <input
              type="file"
              className="sr-only"
              accept={isImage ? `${IMAGE_ACCEPT},${DOCUMENT_ACCEPT}` : DOCUMENT_ACCEPT}
              disabled={locked || component.files.length >= fileLimit}
              onChange={handleFile}
            />
          </label>
        </div>
        {component.files.length ? (
          <ul className="dsn-files__list">
            {component.files.map((file) => (
              <li key={file.id}>
                <span className="dsn-files__name">{file.filename}</span>
                <span className="dsn-files__size">{formatBytes(file.file_size_bytes)}</span>
                <button
                  type="button"
                  className="dsn-icon-btn"
                  onClick={() => removeFile(file.id)}
                  disabled={locked}
                  aria-label={`Remove ${file.filename}`}
                >
                  <X size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="dsn-hint">
            {isImage
              ? 'Optional. A PNG, JPEG, or WebP guides the image; documents add context.'
              : 'Optional. PDF, markdown, text, or CSV. Facts come only from what you attach and write here.'}
          </p>
        )}
      </div>

      {isImage ? (
        <div className="dsn-settings">
          <label className="dsn-setting">
            <span className="as-console__field-label dsn-label-sm">Provider</span>
            <select
              className="as-console__select as-console__select--sm dsn-select"
              value={provider}
              disabled={locked}
              onChange={(event) => {
                const next = catalog.image.providers.find((item) => item === event.target.value)
                if (next) saveSettings({ provider: next })
              }}
            >
              {catalog.image.providers.map((item) => (
                <option key={item} value={item}>
                  {PROVIDER_LABELS[item]}
                </option>
              ))}
            </select>
          </label>
          <label className="dsn-setting">
            <span className="as-console__field-label dsn-label-sm">Model</span>
            <select
              className="as-console__select as-console__select--sm dsn-select"
              value={component.settings.model ?? catalog.image.default_models[provider]}
              disabled={locked}
              onChange={(event) => saveSettings({ model: event.target.value })}
            >
              {catalog.image.models[provider].map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </label>
          <label className="dsn-setting">
            <span className="as-console__field-label dsn-label-sm">Aspect ratio</span>
            <select
              className="as-console__select as-console__select--sm dsn-select"
              value={component.settings.aspect_ratio ?? 'auto'}
              disabled={locked}
              onChange={(event) => saveSettings({ aspect_ratio: event.target.value })}
            >
              {catalog.image.aspect_ratios.map((ratio) => (
                <option key={ratio} value={ratio}>
                  {ratio === 'auto' ? 'Auto (fit section)' : ratio}
                </option>
              ))}
            </select>
          </label>
          {provider === 'openai' ? (
            <label className="dsn-setting">
              <span className="as-console__field-label dsn-label-sm">Quality</span>
              <select
                className="as-console__select as-console__select--sm dsn-select"
                value={component.settings.quality ?? 'high'}
                disabled={locked}
                onChange={(event) => saveSettings({ quality: event.target.value })}
              >
                {catalog.image.qualities.map((quality) => (
                  <option key={quality} value={quality}>
                    {quality}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="dsn-setting">
              <span className="as-console__field-label dsn-label-sm">Resolution</span>
              <select
                className="as-console__select as-console__select--sm dsn-select"
                value={component.settings.image_size ?? '2K'}
                disabled={locked}
                onChange={(event) => saveSettings({ image_size: event.target.value })}
              >
                {catalog.image.image_sizes.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      ) : null}

      {version?.model ? (
        <p className="dsn-component__meta">
          v{version.version} · {version.provider ?? 'model'} {version.model}
        </p>
      ) : null}
    </article>
  )
}
