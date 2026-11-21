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

/** How many book pages show at once. Desktop uses a two-page spread; phones use one. */
export type PagesPerView = 1 | 2

export function spreadsForColumns(columns: number, pagesPerView: PagesPerView = 2): number {
  return Math.max(1, Math.ceil(columns / pagesPerView))
}

export function columnStride(
  viewportWidth: number,
  gap: number,
  pagesPerView: PagesPerView = 2,
): number {
  return (viewportWidth + gap) / pagesPerView
}

/** Same extent math the reader uses on a measured column flow. */
export function columnCountFromExtent(
  extent: number,
  viewportWidth: number,
  gap: number,
  pagesPerView: PagesPerView = 2,
): number {
  const stride = columnStride(viewportWidth, gap, pagesPerView)
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
  pagesPerView: PagesPerView = 2,
): SpreadLocation | null {
  if (columnCounts.length === 0) return null
  let remaining = Math.max(0, Math.floor(globalSpread))
  for (let index = 0; index < columnCounts.length; index += 1) {
    const columns = columnCounts[index]
    if (columns == null) return null
    const spreads = spreadsForColumns(columns, pagesPerView)
    if (remaining < spreads) return { chapterIndex: index, localSpread: remaining }
    remaining -= spreads
  }
  const last = columnCounts.length - 1
  const lastColumns = columnCounts[last]
  if (lastColumns == null) return null
  return { chapterIndex: last, localSpread: spreadsForColumns(lastColumns, pagesPerView) - 1 }
}

/** Inverse of locateSpread. Null when a chapter before this one is unmeasured. */
export function globalSpread(
  columnCounts: readonly (number | undefined)[],
  chapterIndex: number,
  localSpread: number,
  pagesPerView: PagesPerView = 2,
): number | null {
  if (chapterIndex < 0 || chapterIndex >= columnCounts.length) return null
  let total = 0
  for (let index = 0; index < chapterIndex; index += 1) {
    const columns = columnCounts[index]
    if (columns == null) return null
    total += spreadsForColumns(columns, pagesPerView)
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

/**
 * 1-based page numbers for the spread on screen.
 * A chapter with an odd column count ends on a left-hand page. The blank
 * facing page is not a page of the book, so it must not advance the folio
 * or the progress percent.
 */
export function spreadPageNumbers(
  columnCounts: readonly (number | undefined)[],
  chapterIndex: number,
  localSpread: number,
  pagesPerView: PagesPerView = 2,
): { left: number; right: number } | null {
  if (chapterIndex < 0 || chapterIndex >= columnCounts.length) return null
  let start = 0
  for (let index = 0; index < chapterIndex; index += 1) {
    const columns = columnCounts[index]
    if (columns == null) return null
    start += columns
  }
  const columns = columnCounts[chapterIndex]
  if (columns == null || columns <= 0) return null
  const spread = Math.min(
    Math.max(0, Math.floor(localSpread)),
    spreadsForColumns(columns, pagesPerView) - 1,
  )
  const localLeft = spread * pagesPerView
  const leftIndex = start + Math.min(localLeft, columns - 1)
  const rightIndex = start + Math.min(localLeft + (pagesPerView - 1), columns - 1)
  return { left: leftIndex + 1, right: rightIndex + 1 }
}

/**
 * Progress label for the furthest page on screen.
 * Whole percents make every turn look like +1% once a spread is worth less
 * than a point, which is any book longer than 200 pages. Those books show
 * tenths so the label moves by the real fraction of the book.
 */
export function readerProgressLabel(pageReached: number, pageCount: number): string {
  if (!(pageCount > 0) || !(pageReached > 0)) return '0%'
  const reached = Math.min(pageReached, pageCount)
  const pct = (reached / pageCount) * 100
  if (pct >= 99.95) return '100%'
  if (pageCount > 200) {
    const tenths = Math.round(pct * 10) / 10
    if (tenths >= 100) return '100%'
    return `${tenths.toFixed(1)}%`
  }
  return `${Math.round(pct)}%`
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
