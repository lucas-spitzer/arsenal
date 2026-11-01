import type { Block, WordBlock } from './readerContent'

export type ReaderChapter = {
  index: number
  title: string
  blocks: Block[]
}

/** One slice per chapter heading. Text before the first heading stays in chapter 0. */
export function splitReaderChapters(blocks: readonly Block[]): ReaderChapter[] {
  if (blocks.length === 0) return []
  const chapters: ReaderChapter[] = []
  let current: Block[] = []

  const push = () => {
    if (current.length === 0) return
    const first = current[0]
    chapters.push({
      index: chapters.length,
      title: first.chapterTitle || first.text,
      blocks: current,
    })
  }

  for (const block of blocks) {
    if (block.isChapterStart && current.length > 0) {
      push()
      current = []
    }
    current.push(block)
  }
  push()
  return chapters
}

export function spreadsForColumns(columns: number): number {
  return Math.max(1, Math.ceil(columns / 2))
}

export function columnStride(viewportWidth: number, gap: number): number {
  return (viewportWidth + gap) / 2
}

/** Same extent math the reader uses on a measured column flow. */
export function columnCountFromExtent(extent: number, viewportWidth: number, gap: number): number {
  const stride = columnStride(viewportWidth, gap)
  if (stride <= 0) return 1
  return Math.max(1, Math.round((extent + gap) / stride))
}

export type SpreadLocation = { chapterIndex: number; localSpread: number }

/**
 * Map a book-wide spread index onto a chapter. Returns null while an earlier
 * chapter's column count is still unknown, so a bookmark can wait.
 */
export function locateSpread(
  columnCounts: readonly (number | undefined)[],
  globalSpread: number,
): SpreadLocation | null {
  if (columnCounts.length === 0) return null
  let remaining = Math.max(0, Math.floor(globalSpread))
  for (let index = 0; index < columnCounts.length; index += 1) {
    const columns = columnCounts[index]
    if (columns == null) return null
    const spreads = spreadsForColumns(columns)
    if (remaining < spreads) return { chapterIndex: index, localSpread: remaining }
    remaining -= spreads
  }
  const last = columnCounts.length - 1
  const lastColumns = columnCounts[last]
  if (lastColumns == null) return null
  return { chapterIndex: last, localSpread: spreadsForColumns(lastColumns) - 1 }
}

/** Inverse of locateSpread. Null when a chapter before this one is unmeasured. */
export function globalSpread(
  columnCounts: readonly (number | undefined)[],
  chapterIndex: number,
  localSpread: number,
): number | null {
  if (chapterIndex < 0 || chapterIndex >= columnCounts.length) return null
  let total = 0
  for (let index = 0; index < chapterIndex; index += 1) {
    const columns = columnCounts[index]
    if (columns == null) return null
    total += spreadsForColumns(columns)
  }
  return total + Math.max(0, localSpread)
}

export function totalColumns(columnCounts: readonly (number | undefined)[]): number | null {
  if (columnCounts.length === 0) return null
  let total = 0
  for (const columns of columnCounts) {
    if (columns == null) return null
    total += columns
  }
  return total
}

export function chapterIndexForSeq(chapters: readonly ReaderChapter[], seq: number): number {
  for (let index = 0; index < chapters.length; index += 1) {
    if (chapters[index].blocks.some((block) => block.seq === seq)) return index
  }
  return 0
}

export function wordBlocksForChapter(
  wordBlocks: readonly WordBlock[],
  chapter: ReaderChapter | undefined,
): WordBlock[] {
  if (!chapter) return []
  const ids = new Set(chapter.blocks.map((block) => block.id))
  return wordBlocks.filter((wordBlock) => ids.has(wordBlock.block.id))
}

export function seqForSpoken(wordBlocks: readonly WordBlock[], spoken: number): number {
  for (const wordBlock of wordBlocks) {
    for (const word of wordBlock.words) {
      if (word.global === spoken) return word.seq
    }
  }
  return -1
}

export function nextUnmeasuredChapter(
  chapterCount: number,
  columnCounts: readonly (number | undefined)[],
  visibleChapter: number,
): number {
  for (let index = 0; index < chapterCount; index += 1) {
    if (index === visibleChapter) continue
    if (columnCounts[index] == null) return index
  }
  return -1
}
