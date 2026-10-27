import type {
  Lesson,
  LessonIndexStatus,
  LessonObjective,
  LessonObjectiveInput,
  LessonResource,
} from './lessonsApi'

const NUMBERED_LINE = /^\s*\d+\s*[.)]\s*/
const TRAILING_CODE = /\(\s*([A-Z]{2,}(?:-[A-Z0-9]+)+[a-z]?)\s*\)\s*$/
const ASYNC_TAG = /\[\s*async\s*\]/i
const HEADER_LINE = /^\s*enabling learning objective/i

/**
 * Turns pasted ELO text into structured objectives. Accepts one ELO per line
 * like `1. Without the aid of references, ... [Async] (MCS-CMBH-1002a)`.
 * When lines are numbered, unnumbered lines continue the previous ELO
 * (text copied from a PDF often wraps mid-sentence).
 */
export function parseObjectiveLines(text: string): LessonObjectiveInput[] {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !HEADER_LINE.test(line))
  const numbered = lines.some((line) => NUMBERED_LINE.test(line))

  const raw: string[] = []
  for (const line of lines) {
    if (numbered && !NUMBERED_LINE.test(line) && raw.length > 0) {
      raw[raw.length - 1] = `${raw[raw.length - 1]} ${line}`
    } else {
      raw.push(line.replace(NUMBERED_LINE, ''))
    }
  }

  return raw
    .map((line) => {
      let rest = line
      const codeMatch = rest.match(TRAILING_CODE)
      const code = codeMatch ? codeMatch[1] : null
      if (codeMatch) rest = rest.slice(0, codeMatch.index)
      const isAsync = ASYNC_TAG.test(rest)
      rest = rest.replace(ASYNC_TAG, ' ')
      return { text: rest.replace(/\s+/g, ' ').trim(), code, is_async: isAsync }
    })
    .filter((objective) => objective.text)
}

/** Inverse of parseObjectiveLines, for editing an existing class. */
export function objectivesToText(objectives: Pick<LessonObjective, 'text' | 'code' | 'is_async'>[]): string {
  return objectives
    .map((objective, index) => {
      const tag = objective.is_async ? ' [Async]' : ''
      const code = objective.code ? ` (${objective.code})` : ''
      return `${index + 1}. ${objective.text}${tag}${code}`
    })
    .join('\n')
}

export type LessonMatch = {
  lesson: Lesson
  objectives: LessonObjective[]
  /** True when the class title itself matched, so every ELO is shown. */
  titleMatched: boolean
}

export function filterLessons(lessons: Lesson[], query: string): LessonMatch[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return lessons.map((lesson) => ({ lesson, objectives: lesson.objectives, titleMatched: false }))

  const matches: LessonMatch[] = []
  for (const lesson of lessons) {
    if (lesson.title.toLowerCase().includes(needle)) {
      matches.push({ lesson, objectives: lesson.objectives, titleMatched: true })
      continue
    }
    const objectives = lesson.objectives.filter(
      (objective) =>
        objective.text.toLowerCase().includes(needle) ||
        (objective.code ?? '').toLowerCase().includes(needle),
    )
    if (objectives.length > 0) matches.push({ lesson, objectives, titleMatched: false })
  }
  return matches
}

export function lessonStats(lessons: Lesson[]): { classes: number; elos: number; async: number } {
  let elos = 0
  let async = 0
  for (const lesson of lessons) {
    elos += lesson.objectives.length
    async += lesson.objectives.filter((objective) => objective.is_async).length
  }
  return { classes: lessons.length, elos, async }
}

export function formatFileSize(bytes: number | null): string | null {
  if (bytes == null || bytes < 0) return null
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  const mb = bytes / (1024 * 1024)
  return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`
}

const TYPE_LABELS: Record<string, string> = {
  pdf: 'PDF',
  ppt: 'PPT',
  pptx: 'PPTX',
  doc: 'DOC',
  docx: 'DOCX',
  xls: 'XLS',
  xlsx: 'XLSX',
  txt: 'TXT',
  png: 'PNG',
  jpg: 'JPG',
  jpeg: 'JPG',
}

export function fileTypeLabel(resource: Pick<LessonResource, 'kind' | 'filename'>): string {
  if (resource.kind === 'link') return 'Link'
  const extension = resource.filename?.split('.').pop()?.toLowerCase() ?? ''
  return TYPE_LABELS[extension] ?? 'File'
}

export const LESSON_FILE_ACCEPT =
  '.pdf,.ppt,.pptx,.doc,.docx,.xls,.xlsx,.txt,.png,.jpg,.jpeg'

export function indexStatusLabel(resource: Pick<LessonResource, 'kind' | 'index_status'>): string {
  if (resource.kind === 'link') return 'Not searchable (login required)'
  const labels: Record<LessonIndexStatus, string> = {
    pending: 'Queued',
    indexing: 'Indexing',
    ready: 'Searchable',
    failed: 'Index failed',
    skipped: 'Not searchable',
  }
  return labels[resource.index_status]
}

/** Opening message for a "Discuss this class" thread. */
export function lessonSeedPrompt(lesson: Lesson): string {
  if (lesson.objectives.length === 0) {
    return `Let's work through ${lesson.title}. What part of the class do you want to start with?`
  }
  const list = lesson.objectives
    .map((objective) => {
      const code = objective.code ? ` (${objective.code})` : ''
      return `${objective.position}. ${objective.text}${code}`
    })
    .join('\n')
  return (
    `Let's work through ${lesson.title}. Its ELOs:\n\n${list}\n\n` +
    'Which ELO do you want to start with? Reply with its number, or ask anything about the class.'
  )
}
