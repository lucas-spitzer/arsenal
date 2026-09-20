import type { DocumentChapter, NdrSegment } from './sourcesApi'

// The Reader's display model: one block per ndr_segment, with the H1/H2
// hierarchy recovered from document_chapters.

export type Block = {
  seq: number // ndr_segments.sequence_index — the stable deep-link anchor
  id: string // ndr_segments.id (segment UUID); synthetic for the demo passage
  kind: 'heading' | 'paragraph'
  level: 0 | 1 | 2 // 0 = body, 1 = chapter title, 2 = section heading
  variant?: 'list_item' | 'table' | 'caption'
  text: string
  md: string | null // markdown-faithful copy when the API provides it
  chapterTitle: string
  isChapterStart: boolean
}

// --- Demo content ----------------------------------------------------------
// Self-contained sample passage shown when the reader is opened without a
// source (rail navigation): the full UX works without any live data.
export const MOCK_BLOCKS: Block[] = [
  { seq: 0, id: 'mock-0', kind: 'heading', level: 1, text: 'The Architecture of Memory', md: null, chapterTitle: 'The Architecture of Memory', isChapterStart: true },
  { seq: 1, id: 'mock-1', kind: 'paragraph', level: 0, text: 'Memory is not a single faculty but a federation of systems, each tuned to a different kind of remembering. The brain does not store experience the way a tape records sound; it reconstructs it, assembling a usable past out of fragments distributed across the cortex. What feels like retrieval is closer to rebuilding.', md: null, chapterTitle: 'The Architecture of Memory', isChapterStart: false },
  { seq: 2, id: 'mock-2', kind: 'heading', level: 2, text: 'Encoding and consolidation', md: null, chapterTitle: 'The Architecture of Memory', isChapterStart: false },
  { seq: 3, id: 'mock-3', kind: 'paragraph', level: 0, text: 'When you first meet a new idea, it lives in a fragile, short-lived state. Sleep and spaced rehearsal then move it into longer storage through consolidation. This is why cramming feels productive but fades fast: the material never makes the journey from working memory into durable form, and the next morning the scaffolding is gone.', md: null, chapterTitle: 'The Architecture of Memory', isChapterStart: false },
  { seq: 4, id: 'mock-4', kind: 'paragraph', level: 0, text: 'The hippocampus acts as an index rather than a vault. It binds the scattered traces of an event so they can later be reassembled, then gradually hands the relationship over to the cortex itself. Over weeks and months a memory becomes less dependent on its original index and more woven into the fabric of what you already know.', md: null, chapterTitle: 'The Architecture of Memory', isChapterStart: false },
  { seq: 5, id: 'mock-5', kind: 'heading', level: 1, text: 'Retrieval as Reconstruction', md: null, chapterTitle: 'Retrieval as Reconstruction', isChapterStart: true },
  { seq: 6, id: 'mock-6', kind: 'paragraph', level: 0, text: 'Every act of recall changes the thing recalled. Bringing a memory to mind reopens it, and when it settles again it carries a faint imprint of the present moment. This plasticity is not a flaw. It is what lets the past stay useful, updating old lessons against new evidence instead of preserving them like insects in amber.', md: null, chapterTitle: 'Retrieval as Reconstruction', isChapterStart: false },
  { seq: 7, id: 'mock-7', kind: 'heading', level: 2, text: 'The testing effect', md: null, chapterTitle: 'Retrieval as Reconstruction', isChapterStart: false },
  { seq: 8, id: 'mock-8', kind: 'paragraph', level: 0, text: 'Trying to retrieve an answer strengthens the trace far more than rereading it. The effort of reaching, even when you fail, tells the brain that this is information worth keeping. A quiz is therefore not only a measurement of learning but an instrument of it, and a passage read aloud and then recalled sticks better than one merely scanned.', md: null, chapterTitle: 'Retrieval as Reconstruction', isChapterStart: false },
  { seq: 9, id: 'mock-9', kind: 'paragraph', level: 0, text: 'Spacing those retrievals compounds the gain. Short, distributed sessions outperform a single long one of equal length, because each return visit forces a reconstruction from a slightly colder start. Difficulty, paradoxically, is the engine: the small struggle to recover what is half-forgotten is precisely what makes it permanent.', md: null, chapterTitle: 'Retrieval as Reconstruction', isChapterStart: false },
]

// --- Live content ----------------------------------------------------------
// Join ndr_segments with document_chapters to recover the H1/H2 hierarchy the
// pipeline persisted: a chapter's first segment is its title heading, each
// sections[].heading_segment_id is a level-2 heading, everything else is body.
export function buildBlocks(segments: NdrSegment[], chapters: DocumentChapter[]): Block[] {
  const chapterTitleBySegment = new Map<string, string>()
  const chapterStartIds = new Set<string>()
  const sectionHeadingIds = new Set<string>()

  for (const chapter of [...chapters].sort((a, b) => a.sequence_index - b.sequence_index)) {
    for (const segmentId of chapter.segment_ids) {
      chapterTitleBySegment.set(segmentId, chapter.title)
    }
    if (chapter.segment_ids.length > 0) chapterStartIds.add(chapter.segment_ids[0])
    for (const section of chapter.sections ?? []) {
      sectionHeadingIds.add(section.heading_segment_id)
    }
  }

  const ordered = [...segments].sort((a, b) => a.sequence_index - b.sequence_index)
  const blocks: Block[] = []
  let runningChapter = ''

  for (const segment of ordered) {
    const mappedTitle = chapterTitleBySegment.get(segment.id)
    if (mappedTitle) runningChapter = mappedTitle

    const isHeading = segment.kind === 'heading'
    let level: 0 | 1 | 2 = 0
    let isChapterStart = false

    if (isHeading) {
      if (chapterStartIds.has(segment.id)) {
        level = 1
        isChapterStart = true
      } else if (sectionHeadingIds.has(segment.id)) {
        level = 2
      } else if (chapters.length === 0) {
        // Legacy source with no chapter rows: treat every heading as a chapter.
        level = 1
        isChapterStart = true
      } else {
        // Heading not registered in any chapter map — render as a section.
        level = 2
      }
      if (level === 1) runningChapter = segment.text
    }

    blocks.push({
      seq: segment.sequence_index,
      id: segment.id,
      kind: isHeading ? 'heading' : 'paragraph',
      level,
      variant:
        segment.kind === 'list_item' || segment.kind === 'table' || segment.kind === 'caption'
          ? segment.kind
          : undefined,
      text: segment.text,
      md: segment.md ?? null,
      chapterTitle: runningChapter || segment.text,
      isChapterStart,
    })
  }

  return blocks
}

// --- Narration model ------------------------------------------------------
// Flatten every body paragraph into a single word stream so playback can walk
// it linearly. Each word knows its block (for page-follow) and its sentence
// (for the reading band) and its global index (for read/speaking state).
export type SpokenWord = {
  text: string
  global: number
  seq: number
  sentence: number
  em: boolean
  strong: boolean
}
export type WordBlock = { block: Block; words: SpokenWord[] }

export type NarrationClip = {
  fetchNarrationId: string
  audioKey: string
  globals: number[]
  timings: { s: number; e: number }[]
  alignmentSource: 'provider' | 'forced' | 'estimated'
}

/** Return the latest timing whose start is at or before media time. */
export function timingIndexAt(
  timings: { s: number; e: number }[],
  mediaTime: number,
): number {
  let low = 0
  let high = timings.length - 1
  let found = -1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    if (timings[middle].s <= mediaTime) {
      found = middle
      low = middle + 1
    } else {
      high = middle - 1
    }
  }
  return found
}

type StyledWord = { text: string; em: boolean; strong: boolean }

// Tokenize a markdown paragraph into words, tracking *em* / **strong** state.
// Marker characters are stripped; each word carries the style of its first
// content character. Word order and count match the plain-text tokenization
// (markers attach to words), which keeps narration indexes aligned.
function styleWords(md: string): StyledWord[] {
  const out: StyledWord[] = []
  let em = false
  let strong = false
  for (const raw of md.split(/\s+/).filter(Boolean)) {
    let cleaned = ''
    let wordEm = em
    let wordStrong = strong
    let sawContent = false
    let i = 0
    while (i < raw.length) {
      if (raw.startsWith('**', i)) {
        strong = !strong
        i += 2
        continue
      }
      if (raw[i] === '*') {
        em = !em
        i += 1
        continue
      }
      if (!sawContent) {
        wordEm = em
        wordStrong = strong
        sawContent = true
      }
      cleaned += raw[i]
      i += 1
    }
    if (cleaned) out.push({ text: cleaned, em: wordEm, strong: wordStrong })
  }
  return out
}

// --- Wiki term linking ------------------------------------------------------
// Match workspace wiki entry labels/aliases against the word stream so the
// Reader can render tappable term links. Positions are expressed as global
// word indexes over segment UUID-anchored blocks — stable across pagination.

export type WikiTermEntry = {
  id: string
  preferred_label: string
  aliases: string[]
  status?: string
}

function normalizeToken(raw: string): string {
  return raw.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '')
}

// Map of global word index -> wiki entry id for every matched label/alias
// occurrence. Longest label wins at any position; matches never overlap.
export function matchWikiTerms(
  wordBlocks: WordBlock[],
  entries: WikiTermEntry[],
): Map<number, string> {
  type Pattern = { entryId: string; tokens: string[] }
  const byFirstToken = new Map<string, Pattern[]>()

  for (const entry of entries) {
    if (entry.status && entry.status !== 'canonical') continue
    for (const label of [entry.preferred_label, ...entry.aliases]) {
      const tokens = label.split(/\s+/).map(normalizeToken).filter(Boolean)
      if (tokens.length === 0) continue
      const existing = byFirstToken.get(tokens[0]) ?? []
      existing.push({ entryId: entry.id, tokens })
      byFirstToken.set(tokens[0], existing)
    }
  }
  if (byFirstToken.size === 0) return new Map()
  for (const patterns of byFirstToken.values()) {
    patterns.sort((a, b) => b.tokens.length - a.tokens.length)
  }

  const result = new Map<number, string>()
  for (const wb of wordBlocks) {
    const words = wb.words
    const normalized = words.map((w) => normalizeToken(w.text))
    for (let i = 0; i < words.length; i += 1) {
      const candidates = byFirstToken.get(normalized[i])
      if (!candidates) continue
      for (const pattern of candidates) {
        if (i + pattern.tokens.length > words.length) continue
        let matched = true
        for (let t = 1; t < pattern.tokens.length; t += 1) {
          if (normalized[i + t] !== pattern.tokens[t]) {
            matched = false
            break
          }
        }
        if (!matched) continue
        for (let t = 0; t < pattern.tokens.length; t += 1) {
          result.set(words[i + t].global, pattern.entryId)
        }
        i += pattern.tokens.length - 1
        break
      }
    }
  }
  return result
}

/** Max words for free-text define selection in the reader. */
export const READER_DEFINE_MAX_WORDS = 8

export type ParagraphNeighbors = {
  prev: string
  current: string
  next: string
}

export type ReaderSelectionContext = {
  term: string
  globals: number[]
  blockId: string
  sentence: string
  neighbors: ParagraphNeighbors
  /** Wiki entry id when every selected word maps to the same canonical term. */
  entryId: string | null
}

function paragraphNeighborsAt(wordBlocks: WordBlock[], index: number): ParagraphNeighbors {
  const current = wordBlocks[index]?.block.kind === 'paragraph' ? wordBlocks[index].block.text : ''
  let prev = ''
  for (let i = index - 1; i >= 0; i -= 1) {
    if (wordBlocks[i].block.kind === 'paragraph') {
      prev = wordBlocks[i].block.text
      break
    }
  }
  let next = ''
  for (let i = index + 1; i < wordBlocks.length; i += 1) {
    if (wordBlocks[i].block.kind === 'paragraph') {
      next = wordBlocks[i].block.text
      break
    }
  }
  return { prev, current, next }
}

function sentenceForGlobals(words: SpokenWord[], globals: number[]): string {
  if (globals.length === 0) return ''
  const byGlobal = new Map(words.map((w) => [w.global, w]))
  const first = byGlobal.get(globals[0])
  if (!first) return ''
  return words
    .filter((w) => w.sentence === first.sentence && w.seq === first.seq)
    .map((w) => w.text)
    .join(' ')
}

/**
 * Resolve a contiguous same-block word selection into define context.
 * Returns null when empty, multi-block, or over the word cap.
 */
export function resolveReaderSelection(
  wordBlocks: WordBlock[],
  globals: number[],
  termByWord: Map<number, string>,
): ReaderSelectionContext | null {
  if (globals.length === 0 || globals.length > READER_DEFINE_MAX_WORDS) return null
  const sorted = [...new Set(globals)].sort((a, b) => a - b)
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i] !== sorted[i - 1] + 1) return null
  }

  const blockIndex = wordBlocks.findIndex((wb) =>
    wb.words.some((w) => w.global === sorted[0]),
  )
  if (blockIndex < 0) return null
  const wb = wordBlocks[blockIndex]
  if (wb.block.kind !== 'paragraph') return null

  const inBlock = new Map(wb.words.map((w) => [w.global, w]))
  const selected = sorted.map((g) => inBlock.get(g))
  if (selected.some((w) => w == null)) return null
  const words = selected as SpokenWord[]

  const flat = wordBlocks.flatMap((block) => block.words)
  const entryIds = sorted.map((g) => termByWord.get(g) ?? null)
  const entryId =
    entryIds.every((id) => id != null && id === entryIds[0]) ? entryIds[0] : null

  return {
    term: words
      .map((w) => w.text)
      .join(' ')
      .replace(/^[\s"'“”‘’]+|[\s"'“”‘’]+$/gu, ''),
    globals: sorted,
    blockId: wb.block.id,
    sentence: sentenceForGlobals(flat, sorted),
    neighbors: paragraphNeighborsAt(wordBlocks, blockIndex),
    entryId,
  }
}

/**
 * Collect data-global indexes covered by the current DOM selection inside root.
 * Returns [] when the selection is empty or outside root.
 */
export function globalsFromDomSelection(root: HTMLElement | null): number[] {
  if (!root || typeof window === 'undefined') return []
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return []
  const range = sel.getRangeAt(0)
  if (!root.contains(range.commonAncestorContainer)) return []

  const globals: number[] = []
  for (const node of root.querySelectorAll<HTMLElement>('.reader__word[data-global]')) {
    if (!range.intersectsNode(node)) continue
    const g = Number(node.dataset.global)
    if (Number.isFinite(g)) globals.push(g)
  }
  return globals
}

/** True when a token ends a sentence, allowing closing quotes/brackets after .!? */
export function endsSentence(token: string): boolean {
  return /[.!?]["'”’)\]]*$/.test(token)
}

export function buildNarration(blocks: Block[]): { wordBlocks: WordBlock[]; total: number } {
  const wordBlocks: WordBlock[] = []
  let global = 0
  let sentence = 0
  for (const block of blocks) {
    if (block.kind !== 'paragraph') {
      wordBlocks.push({ block, words: [] })
      continue
    }
    // The plain text column is the canonical word stream (it is what narration
    // audio is aligned against). The markdown copy only adds styling — if its
    // tokenization ever disagrees, drop the styling rather than desync.
    const plain = block.text.split(/\s+/).filter(Boolean)
    let styled: StyledWord[] | null = block.md ? styleWords(block.md) : null
    if (styled && styled.length !== plain.length) styled = null

    const words: SpokenWord[] = []
    for (let w = 0; w < plain.length; w += 1) {
      const text = plain[w]
      words.push({
        text: styled ? styled[w].text : text,
        em: styled ? styled[w].em : false,
        strong: styled ? styled[w].strong : false,
        global,
        seq: block.seq,
        sentence,
      })
      global += 1
      if (endsSentence(text)) sentence += 1
    }
    // Paragraphs are hard sentence boundaries so the reading band never leaks
    // across blocks when punctuation is missing or malformed.
    if (words.length > 0) sentence += 1
    wordBlocks.push({ block, words })
  }
  return { wordBlocks, total: global }
}

/** Group paragraph timings that share an audio file into one playable clip. */
export function buildNarrationClips(
  wordBlocks: WordBlock[],
  narration: Map<
    string,
    {
      id: string
      audio_path?: string | null
      alignment_source: 'provider' | 'forced' | 'estimated'
      words: { s: number; e: number }[]
    }
  >,
): NarrationClip[] {
  const clips: NarrationClip[] = []
  for (const wb of wordBlocks) {
    if (wb.words.length === 0) continue
    const row = narration.get(wb.block.id)
    if (!row || row.words.length === 0) continue
    if (row.words.length !== wb.words.length) continue
    const audioKey = row.audio_path || wb.block.id
    const last = clips[clips.length - 1]
    const timings = row.words.map((w) => ({ s: w.s, e: w.e }))
    const globals = wb.words.map((word) => word.global)
    if (
      last
      && last.audioKey === audioKey
      && last.alignmentSource === row.alignment_source
    ) {
      last.globals.push(...globals)
      last.timings.push(...timings)
      continue
    }
    clips.push({
      fetchNarrationId: row.id,
      audioKey,
      globals,
      timings,
      alignmentSource: row.alignment_source,
    })
  }
  return clips
}
