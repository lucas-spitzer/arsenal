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
  prompts: DiscussionPrompt[]
}

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
export function discussionSections(
  entries: WikiEntry[],
  sourceId: string | null = null,
): DiscussionSection[] {
  type Bucket = {
    key: string
    title: string
    titleUpdatedAt: string
    createdAt: string
    prompts: Array<DiscussionPrompt & { order: number; createdAt: string }>
  }
  const groups = new Map<string, Bucket>()

  for (const entry of entries) {
    if (entry.entry_kind !== 'elo' || entry.status !== 'canonical') continue
    const entrySourceId = sourceIdOf(entry)
    if (sourceId && entrySourceId !== sourceId) continue
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
    existing.prompts.push(item)
  }

  return [...groups.values()]
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt) || left.title.localeCompare(right.title))
    .map((group) => ({
      key: group.key,
      title: group.title,
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
