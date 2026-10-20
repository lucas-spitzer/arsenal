export interface CardEntry {
  entry_kind: string
  definition: string
  items?: { name: string }[]
}

export function listCardBack(entry: CardEntry): string {
  const names = (entry.items ?? []).map((item) => item.name.trim()).filter(Boolean)
  if (names.length === 0) return entry.definition.trim()
  return names.map((name, index) => `${index + 1}. ${name}`).join('\n')
}

export function definitionCardBack(entry: CardEntry): string {
  if (entry.entry_kind === 'list') return listCardBack(entry)
  return entry.definition.trim()
}
