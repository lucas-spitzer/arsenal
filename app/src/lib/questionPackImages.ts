/** Images a Design Forge question pack names, and which ones the author attached. */

export const MAX_QUESTION_IMAGES = 25
export const IMAGE_ACCEPT = '.png,.jpg,.jpeg,.webp'

export interface ImageStatus {
  attached: string[]
  missing: string[]
  unused: string[]
}

/** File names a pack's questions point at, in order. Unreadable JSON names none. */
export function questionImageNames(jsonText: string): string[] {
  let payload: unknown
  try {
    payload = JSON.parse(jsonText)
  } catch {
    return []
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return []
  const questions = (payload as { questions?: unknown }).questions
  if (!Array.isArray(questions)) return []
  const names: string[] = []
  for (const question of questions) {
    const name = imageName(question)
    if (name && !names.includes(name)) names.push(name)
  }
  return names
}

function imageName(question: unknown): string | null {
  if (!question || typeof question !== 'object') return null
  const image = (question as { image?: unknown }).image
  if (typeof image === 'string') return image.trim() || null
  if (image && typeof image === 'object') {
    const filename = (image as { filename?: unknown }).filename
    return typeof filename === 'string' ? filename.trim() || null : null
  }
  return null
}

export function imageStatus(needed: string[], files: { name: string }[]): ImageStatus {
  const have = new Set(files.map((file) => file.name))
  const wanted = new Set(needed)
  return {
    attached: needed.filter((name) => have.has(name)),
    missing: needed.filter((name) => !have.has(name)),
    unused: files.map((file) => file.name).filter((name) => !wanted.has(name)),
  }
}

/** Add picked files. A same-name file replaces the earlier one; the list stops at `limit`. */
export function mergeImages<T extends { name: string }>(
  current: T[],
  added: T[],
  limit = MAX_QUESTION_IMAGES,
): { files: T[]; dropped: number } {
  const files = [...current]
  let dropped = 0
  for (const file of added) {
    const at = files.findIndex((item) => item.name === file.name)
    if (at >= 0) files[at] = file
    else if (files.length < limit) files.push(file)
    else dropped += 1
  }
  return { files, dropped }
}
