export interface CardEntry {
  entry_kind: string
  definition: string
  significance?: string | null
  items?: { name: string }[]
}

export function listCardBack(entry: CardEntry): string {
  const names = (entry.items ?? []).map((item) => item.name.trim()).filter(Boolean)
  if (names.length === 0) return entry.definition.trim()
  return names.map((name, index) => `${index + 1}. ${name}`).join('\n')
}

export function definitionCardBack(entry: CardEntry): string {
  if (entry.entry_kind === 'list') return listCardBack(entry)
  const definition = entry.definition.trim()
  if (entry.entry_kind === 'abbreviation') {
    const title = (entry.significance ?? '').trim()
    if (title && definition) return `${title}\n${definition}`
    return title || definition
  }
  return definition
}
