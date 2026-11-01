import type { WikiEntry } from './workspaceApi'

export type DiscussionPrompt = {
  key: string
  sourceId: string | null
  title: string
  prompt: string
}

export type DiscussionSection = {
  key: string
  title: string
  sourceId: string | null
  createdAt: string
  prompts: DiscussionPrompt[]
}

export type DiscussionSourceGroup = {
  sourceId: string | null
  name: string
  sections: DiscussionSection[]
}

export const UNASSIGNED_SOURCE_NAME = 'Unassigned'

function originString(origin: Record<string, unknown>, key: string): string | null {
  const value = origin[key]
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

function originIndex(origin: Record<string, unknown>): number | null {
  const value = origin.elo_index
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function sourceIdOf(entry: WikiEntry): string | null {
  const evidence = entry.evidence.find((item) => item.source_id)
  return evidence?.source_id ?? null
}

/** Canonical ELOs grouped by the knowledge upload that introduced them. */
export function discussionSections(entries: WikiEntry[]): DiscussionSection[] {
  type Bucket = {
    key: string
    title: string
    titleUpdatedAt: string
    sourceId: string | null
    createdAt: string
    prompts: Array<DiscussionPrompt & { order: number; createdAt: string }>
  }
  const groups = new Map<string, Bucket>()

  for (const entry of entries) {
    if (entry.entry_kind !== 'elo' || entry.status !== 'canonical') continue
    const entrySourceId = sourceIdOf(entry)
    const prompt = entry.preferred_label.trim()
    if (!prompt) continue

    const key =
      originString(entry.origin, 'knowledge_project_id') ??
      originString(entry.origin, 'batch_id') ??
      entry.id
    const title = originString(entry.origin, 'section_title') ?? 'Untitled'
    const order = originIndex(entry.origin)
    const existing = groups.get(key)
    const item = {
      key: entry.id,
      sourceId: entrySourceId,
      title: prompt,
      prompt,
      order: order ?? Number.MAX_SAFE_INTEGER,
      createdAt: entry.created_at,
    }
    if (!existing) {
      groups.set(key, {
        key,
        title,
        titleUpdatedAt: entry.updated_at,
        sourceId: entrySourceId,
        createdAt: entry.created_at,
        prompts: [item],
      })
      continue
    }
    if (entry.created_at < existing.createdAt) existing.createdAt = entry.created_at
    if (entry.updated_at >= existing.titleUpdatedAt) {
      existing.title = title
      existing.titleUpdatedAt = entry.updated_at
    }
    existing.sourceId ??= entrySourceId
    existing.prompts.push(item)
  }

  return [...groups.values()]
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt) || left.title.localeCompare(right.title))
    .map((group) => ({
      key: group.key,
      title: group.title,
      sourceId: group.sourceId,
      createdAt: group.createdAt,
      prompts: group.prompts
        .sort(
          (left, right) =>
            left.order - right.order ||
            left.createdAt.localeCompare(right.createdAt) ||
            left.key.localeCompare(right.key),
        )
        .map(({ key, sourceId: promptSourceId, title, prompt }) => ({
          key,
          sourceId: promptSourceId,
          title,
          prompt,
        })),
    }))
}

/**
 * Batches grouped under their source, sources sorted by name. Batches keep the
 * order from `discussionSections` (oldest first). A batch whose source is
 * missing or unknown falls under "Unassigned", listed last.
 */
export function discussionSourceGroups(
  sections: DiscussionSection[],
  sources: ReadonlyArray<{ id: string; name: string }>,
): DiscussionSourceGroup[] {
  const names = new Map(sources.map((source) => [source.id, source.name]))
  const groups = new Map<string | null, DiscussionSourceGroup>()

  for (const section of sections) {
    const name = section.sourceId ? names.get(section.sourceId) : undefined
    const sourceId = name ? section.sourceId : null
    const existing = groups.get(sourceId)
    if (existing) {
      existing.sections.push(section)
      continue
    }
    groups.set(sourceId, { sourceId, name: name ?? UNASSIGNED_SOURCE_NAME, sections: [section] })
  }

  return [...groups.values()].sort((left, right) => {
    if (left.sourceId === null) return 1
    if (right.sourceId === null) return -1
    return left.name.localeCompare(right.name)
  })
}
