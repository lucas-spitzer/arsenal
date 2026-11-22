export interface CardEntry {
  entry_kind: string
  definition: string
  significance?: string | null
  aliases?: string[]
  items?: { name: string; details?: string; a?: string; b?: string }[]
}

export function listCardBack(entry: CardEntry): string {
  const names = (entry.items ?? []).map((item) => item.name.trim()).filter(Boolean)
  if (names.length === 0) return entry.definition.trim()
  return names.map((name, index) => `${index + 1}. ${name}`).join('\n')
}

export function compareCardBack(entry: CardEntry): string {
  const poles = (entry.aliases ?? []).map((alias) => alias.trim()).filter(Boolean)
  const left = poles[0] ?? 'A'
  const right = poles[1] ?? 'B'
  const lines = (entry.items ?? [])
    .map((item) => {
      const dimension = item.name.trim()
      const aText = (item.a ?? '').trim()
      const bText = (item.b ?? '').trim()
      if (!dimension || !aText || !bText) return ''
      return `${dimension} — ${left}: ${aText} · ${right}: ${bText}`
    })
    .filter(Boolean)
  if (lines.length === 0) return entry.definition.trim()
  return lines.join('\n')
}

export function definitionCardBack(entry: CardEntry): string {
  if (entry.entry_kind === 'list') return listCardBack(entry)
  if (entry.entry_kind === 'compare') return compareCardBack(entry)
  const definition = entry.definition.trim()
  if (entry.entry_kind === 'abbreviation') {
    const title = (entry.significance ?? '').trim()
    if (title && definition) return `${title}\n${definition}`
    return title || definition
  }
  return definition
}
