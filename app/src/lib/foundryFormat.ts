export type Module = 'intellex' | 'mathesys' | 'qngen'

export const moduleLabels: Record<Module, string> = {
  intellex: 'Intellex',
  mathesys: 'Mathesys',
  qngen: 'QnGen',
}

const documentTypeLabels: Record<string, string> = {
  military_doctrine: 'Doctrinal Publication',
  research_paper: 'Research Paper',
  white_paper: 'White Paper',
  report: 'Report',
  unknown: 'Unknown',
}

export function documentTypeLabel(type: string): string {
  return (
    documentTypeLabels[type] ??
    type
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  )
}

const artifactKindLabels: Record<string, string> = {
  electronic_book: 'Electronic Book',
  wiki_json: 'Wiki Export',
  narration_audio: 'Audio Narration',
  study_sheet: 'Study Sheet',
  wiki_knowledge: 'Wiki Knowledge',
  lesson: 'Lesson Module',
  assessment: 'Assessment Bank',
  concept_map: 'Concept Map',
  flashcards: 'Flashcards',
  quizzes: 'Quizzes',
  scenarios: 'Scenarios',
}

const artifactKindShortLabels: Record<string, string> = {
  electronic_book: 'EBook',
  wiki_json: 'Wiki JSON',
  narration_audio: 'Audio Narration',
  study_sheet: 'Study Sheet',
  wiki_knowledge: 'Wiki',
  lesson: 'Lesson',
  assessment: 'Assessment',
  concept_map: 'Concept Map',
  flashcards: 'Flashcards',
  quizzes: 'Quizzes',
  scenarios: 'Scenarios',
}

export function artifactKindLabel(kind: string): string {
  return artifactKindLabels[kind] ?? kind.replace(/_/g, ' ')
}

export function artifactKindShortLabel(kind: string): string {
  return artifactKindShortLabels[kind] ?? artifactKindLabel(kind)
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function formatDuration(sec: number): string {
  if (sec < 60) return `${sec}s`
  const minutes = Math.floor(sec / 60)
  const seconds = sec % 60
  if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

export function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatCostUsd(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return '—'
  if (amount < 0.01) return `$${amount.toFixed(4)}`
  if (amount < 1) return `$${amount.toFixed(3)}`
  return `$${amount.toFixed(2)}`
}

export function formatCredits(count: number): string {
  if (!Number.isFinite(count) || count <= 0) return '—'
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(2)}M`
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`
  return String(count)
}

export function mimeLabel(mimeType: string): string {
  const parts = mimeType.split('/')
  const subtype = parts[parts.length - 1] ?? mimeType
  return subtype.toUpperCase()
}

const artifactFormatLabels: Record<string, string> = {
  epub3: 'EPUB',
}

export function artifactFormatLabel(format: string): string {
  if (artifactFormatLabels[format]) {
    return artifactFormatLabels[format]
  }
  return format.replace(/\d+$/, '').toUpperCase()
}
