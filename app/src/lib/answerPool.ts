// Randomizable answers for a quiz question.
//
// A pool holds several phrasings of the correct answer and more distractors
// than one rendering shows. The study view draws from it per session so a
// learner cannot memorize option order or wording.

export interface AnswerPoolDistractor {
  text: string
  misconception?: string
  confused_with_wiki_id?: string | null
}

export interface AnswerPool {
  correct: string[]
  distractors: AnswerPoolDistractor[]
  show_count: number
}

export interface DrawnQuestion {
  /** Replacement stem, only for true/false pools where the statement is the question. */
  question: string | null
  options: string[]
  correct: string[]
}

export type Rng = () => number

const TRUE_FALSE = new Set(['true_false_correction', 'true_false'])
const MULTIPLE_SELECT = 'multiple_select'

export function emptyPool(showCount = 4): AnswerPool {
  return { correct: [], distractors: [], show_count: showCount }
}

export function hasPool(raw: unknown): raw is AnswerPool {
  if (!raw || typeof raw !== 'object') return false
  const pool = raw as Partial<AnswerPool>
  const correct = Array.isArray(pool.correct) ? pool.correct : []
  const distractors = Array.isArray(pool.distractors) ? pool.distractors : []
  return correct.length > 0 || distractors.length > 0
}

/** Fold a stable id into a session seed so each question keeps its own draw. */
export function combineSeed(seed: number, key: string): number {
  let hash = seed >>> 0
  for (let i = 0; i < key.length; i += 1) {
    hash = Math.imul(hash ^ key.charCodeAt(i), 0x5bd1e995)
  }
  return hash >>> 0
}

/** Deterministic generator (mulberry32) so a session keeps one shuffle across renders. */
export function seededRng(seed: number): Rng {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function shuffle<T>(items: T[], rng: Rng): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

function sample<T>(items: T[], count: number, rng: Rng): T[] {
  return shuffle(items, rng).slice(0, Math.max(0, count))
}

export function drawOptions(pool: AnswerPool, subtype: string | null | undefined, rng: Rng = Math.random): DrawnQuestion {
  const correct = pool.correct.filter((text) => text.trim())
  const distractors = pool.distractors.map((row) => row.text).filter((text) => text.trim())
  const kind = subtype ?? 'multiple_choice'

  if (TRUE_FALSE.has(kind)) {
    const statements = [
      ...correct.map((text) => ({ text, isTrue: true })),
      ...distractors.map((text) => ({ text, isTrue: false })),
    ]
    if (statements.length === 0) return { question: null, options: [], correct: [] }
    const picked = statements[Math.floor(rng() * statements.length)]
    return { question: picked.text, options: ['True', 'False'], correct: [picked.isTrue ? 'True' : 'False'] }
  }

  if (correct.length === 0) return { question: null, options: [], correct: [] }
  const show = Math.max(2, pool.show_count || 4)

  if (kind === MULTIPLE_SELECT) {
    const maxCorrect = Math.min(correct.length, Math.max(2, show - 1))
    const minCorrect = Math.min(2, maxCorrect)
    const take = minCorrect + Math.floor(rng() * (maxCorrect - minCorrect + 1))
    const chosen = sample(correct, take, rng)
    const fill = sample(distractors, show - take, rng)
    return { question: null, options: shuffle([...chosen, ...fill], rng), correct: chosen }
  }

  const answer = correct[Math.floor(rng() * correct.length)]
  const fill = sample(distractors, show - 1, rng)
  return { question: null, options: shuffle([answer, ...fill], rng), correct: [answer] }
}

interface Cited {
  id: string
  citations?: { uri?: string }[] | null
}

export function primaryWikiId(item: Cited): string | null {
  for (const citation of item.citations ?? []) {
    const uri = citation?.uri ?? ''
    if (uri.startsWith('wiki://')) return uri.slice('wiki://'.length)
  }
  return null
}

/**
 * Keep one quiz per cited wiki entry, chosen at random, so a session asks each
 * term once. Quizzes without a wiki citation are all kept. Ids in `keep` win
 * their group, which lets a deep link land on the exact question.
 */
export function pickVariants<T extends Cited>(items: T[], rng: Rng = Math.random, keep: Set<string> = new Set()): T[] {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const wikiId = primaryWikiId(item)
    if (!wikiId) continue
    groups.set(wikiId, [...(groups.get(wikiId) ?? []), item])
  }
  const chosen = new Set<string>()
  for (const variants of groups.values()) {
    const kept = variants.find((item) => keep.has(item.id))
    const pick = kept ?? variants[Math.floor(rng() * variants.length)]
    chosen.add(pick.id)
  }
  return items.filter((item) => !primaryWikiId(item) || chosen.has(item.id))
}
