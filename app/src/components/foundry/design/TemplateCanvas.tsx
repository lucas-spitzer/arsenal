import { Lock } from 'lucide-react'
import type { CSSProperties } from 'react'
import {
  catalogAssetUrl,
  COMPONENT_TYPE_LABELS,
  type StudyComponent,
  type StudyMaterialOptions,
  type StudyTemplate,
  type StudyTheme,
  type TemplateSection,
} from '../../../lib/studyMaterialApi'
import { COMPONENT_ICONS } from './componentIcons'

interface TemplateCanvasProps {
  template: StudyTemplate
  theme: StudyTheme
  title: string
  options: StudyMaterialOptions
  components?: StudyComponent[]
  selectedSectionId?: string | null
  onSelect?: (sectionId: string) => void
  mini?: boolean
}

function boxStyle(section: TemplateSection): CSSProperties {
  const { x, y, w, h } = section.box
  return { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` }
}

function strictSummary(section: TemplateSection, options: StudyMaterialOptions): string {
  if (section.kind !== 'strict') return ''
  if (section.content === 'title') return 'Title only'
  if (section.content === 'logo') return options.logo_locked ? 'Locked theme logo' : 'Empty'
  return `Footer text, ${section.max_words ?? 20} words max`
}

function sectionAriaLabel(
  section: TemplateSection,
  options: StudyMaterialOptions,
  count: number,
): string {
  if (section.kind === 'strict') return `${section.label}: ${strictSummary(section, options)}`
  return `${section.label}: ${count} of ${section.max_components} components`
}

function SectionContent({
  section,
  template,
  theme,
  title,
  options,
  components,
  mini,
}: {
  section: TemplateSection
  template: StudyTemplate
  theme: StudyTheme
  title: string
  options: StudyMaterialOptions
  components: StudyComponent[]
  mini: boolean
}) {
  if (section.kind === 'strict') {
    if (section.content === 'title') {
      return <span className="dsn-page__title">{title || 'Title'}</span>
    }
    if (section.content === 'logo') {
      const logo = options.logo_locked
        ? theme.logos.find((item) => item.id === options.logo_id)
        : undefined
      return logo ? (
        <span className="dsn-page__logo">
          <img src={catalogAssetUrl(logo.asset)} alt={mini ? '' : logo.label} />
        </span>
      ) : null
    }
    return (
      <span className="dsn-page__footer">
        <span>{options.footer_text}</span>
        {theme.disclaimer && template.disclaimer === 'footer' ? (
          <span className="dsn-page__disclaimer">{theme.disclaimer}</span>
        ) : null}
      </span>
    )
  }

  return (
    <>
      {components.length === 0 && !mini ? (
        <span className="dsn-page__empty">Select to add components</span>
      ) : null}
      {!mini ? (
        <span className="dsn-page__chips">
          {components.map((component) => {
            const Icon = COMPONENT_ICONS[component.component_type]
            return (
              <span className="dsn-page__chip" key={component.id}>
                <Icon size={14} aria-hidden="true" />
                <span className="dsn-page__chip-type">
                  {COMPONENT_TYPE_LABELS[component.component_type]}
                </span>
                <span className="dsn-page__chip-text">
                  {component.instructions || 'No instructions yet'}
                </span>
              </span>
            )
          })}
        </span>
      ) : null}
      {template.disclaimer === 'per_section' && theme.disclaimer ? (
        <span className="dsn-page__card-disclaimer">{theme.disclaimer}</span>
      ) : null}
    </>
  )
}

export function TemplateCanvas({
  template,
  theme,
  title,
  options,
  components = [],
  selectedSectionId = null,
  onSelect,
  mini = false,
}: TemplateCanvasProps) {
  const { width_in, height_in, margin_in } = template.page
  const pageStyle = {
    aspectRatio: `${width_in} / ${height_in}`,
    padding: `${(margin_in / width_in) * 100}%`,
    '--dsn-title': theme.colors.title ?? theme.colors.heading,
    '--dsn-rule': theme.colors.rule,
    '--dsn-muted': theme.colors.muted,
  } as CSSProperties

  return (
    <div
      className={`dsn-page${mini ? ' dsn-page--mini' : ''}${template.cut_lines ? ' dsn-page--cut' : ''}`}
      style={pageStyle}
      aria-hidden={mini ? true : undefined}
    >
      <div className="dsn-page__safe">
        {template.sections.map((section) => {
          const sectionComponents = components.filter((item) => item.section_id === section.id)
          const className = [
            'dsn-page__section',
            `dsn-page__section--${section.kind === 'strict' ? section.content : 'flexible'}`,
            selectedSectionId === section.id ? 'is-selected' : '',
          ]
            .filter(Boolean)
            .join(' ')
          const content = (
            <SectionContent
              section={section}
              template={template}
              theme={theme}
              title={title}
              options={options}
              components={sectionComponents}
              mini={mini}
            />
          )
          if (mini || !onSelect) {
            return (
              <div key={section.id} className={className} style={boxStyle(section)}>
                {content}
              </div>
            )
          }
          return (
            <button
              key={section.id}
              type="button"
              className={className}
              style={boxStyle(section)}
              onClick={() => onSelect(section.id)}
              aria-pressed={selectedSectionId === section.id}
              aria-label={sectionAriaLabel(section, options, sectionComponents.length)}
            >
              {section.kind === 'strict' ? (
                <Lock className="dsn-page__lock" size={12} aria-hidden="true" />
              ) : null}
              {content}
            </button>
          )
        })}
      </div>
    </div>
  )
}
