import { describe, expect, it } from 'vitest'
import type { Block } from './readerContent'
import { buildNarration } from './readerContent'
import {
  chapterIndexForSeq,
  columnCountFromExtent,
  globalSpread,
  locateSpread,
  nextUnmeasuredChapter,
  readerProgressLabel,
  seqForSpoken,
  splitReaderChapters,
  spreadPageNumbers,
  spreadsForColumns,
  totalColumns,
  wordBlocksForChapter,
} from './readerChapters'

function block(
  seq: number,
  id: string,
  options: { chapterStart?: boolean; title?: string } = {},
): Block {
  const title = options.title ?? 'Chapter'
  return {
    seq,
    id,
    kind: options.chapterStart ? 'heading' : 'paragraph',
    level: options.chapterStart ? 1 : 0,
    text: options.chapterStart ? title : 'Some words here.',
    md: null,
    chapterTitle: title,
    isChapterStart: options.chapterStart ?? false,
  }
}

describe('splitReaderChapters', () => {
  it('keeps a preface as its own slice and starts a new slice at each chapter', () => {
    const chapters = splitReaderChapters([
      block(0, 'preface'),
      block(1, 'c1', { chapterStart: true, title: 'One' }),
      block(2, 'p1'),
      block(3, 'c2', { chapterStart: true, title: 'Two' }),
      block(4, 'p2'),
    ])
    expect(chapters.map((chapter) => chapter.blocks.map((item) => item.id))).toEqual([
      ['preface'],
      ['c1', 'p1'],
      ['c2', 'p2'],
    ])
    expect(chapters[2].title).toBe('Two')
  })
})

describe('column geometry', () => {
  it('counts columns from the flow extent', () => {
    const gap = 48
    const width = 1000
    const stride = (width + gap) / 2
    const extent = stride * 4 - gap
    expect(columnCountFromExtent(extent, width, gap)).toBe(4)
    expect(spreadsForColumns(4)).toBe(2)
  })

  it('locates a book-wide spread once earlier chapters are measured', () => {
    expect(locateSpread([4, 2], 0)).toEqual({ chapterIndex: 0, localSpread: 0 })
    expect(locateSpread([4, 2], 1)).toEqual({ chapterIndex: 0, localSpread: 1 })
    expect(locateSpread([4, 2], 2)).toEqual({ chapterIndex: 1, localSpread: 0 })
    expect(locateSpread([4, 2], 9)).toEqual({ chapterIndex: 1, localSpread: 0 })
    expect(locateSpread([4, undefined], 2)).toBeNull()
    expect(globalSpread([4, 2], 1, 0)).toBe(2)
    expect(globalSpread([4, undefined], 1, 0)).toBe(2)
    expect(globalSpread([undefined, 2], 1, 0)).toBeNull()
    expect(totalColumns([4, 2])).toBe(6)
    expect(totalColumns([4, undefined])).toBeNull()
  })

  it('numbers a spread from real columns and skips a blank facing page', () => {
    expect(spreadPageNumbers([4, 2], 0, 0)).toEqual({ left: 1, right: 2 })
    expect(spreadPageNumbers([4, 2], 1, 0)).toEqual({ left: 5, right: 6 })
    // Chapter of 3 columns: the second spread is a single left-hand page.
    expect(spreadPageNumbers([3, 4], 0, 1)).toEqual({ left: 3, right: 3 })
    expect(spreadPageNumbers([3, 4], 1, 0)).toEqual({ left: 4, right: 5 })
    expect(spreadPageNumbers([3, undefined], 1, 0)).toBeNull()
  })
})

describe('reader progress', () => {
  it('keeps whole percents while one spread is at least 1%', () => {
    expect(readerProgressLabel(2, 40)).toBe('5%')
    expect(readerProgressLabel(4, 40)).toBe('10%')
    expect(readerProgressLabel(40, 40)).toBe('100%')
  })

  it('moves by the real fraction of a long book instead of +1% per turn', () => {
    const pageCount = 240
    const labels: string[] = []
    for (let spread = 0; spread < 6; spread += 1) {
      labels.push(readerProgressLabel(spread * 2 + 2, pageCount))
    }
    expect(labels).toEqual(['0.8%', '1.7%', '2.5%', '3.3%', '4.2%', '5.0%'])
    const values = labels.map((label) => Number(label.replace('%', '')))
    for (let index = 1; index < values.length; index += 1) {
      expect(values[index] - values[index - 1]).toBeLessThan(1)
    }
  })

  it('does not count a blank facing page toward progress', () => {
    const pages = spreadPageNumbers([3], 0, 1)
    expect(pages).toEqual({ left: 3, right: 3 })
    expect(readerProgressLabel(pages?.right ?? 0, 3)).toBe('100%')
  })
})

describe('chapter lookup', () => {
  const chapters = splitReaderChapters([
    block(0, 'c1', { chapterStart: true, title: 'One' }),
    block(1, 'p1'),
    block(2, 'c2', { chapterStart: true, title: 'Two' }),
    block(3, 'p2'),
  ])

  it('finds the chapter and words for a segment', () => {
    expect(chapterIndexForSeq(chapters, 3)).toBe(1)
    const { wordBlocks } = buildNarration(chapters.flatMap((chapter) => chapter.blocks))
    const second = wordBlocksForChapter(wordBlocks, chapters[1])
    expect(second.map((wordBlock) => wordBlock.block.id)).toEqual(['c2', 'p2'])
    const spoken = second[1].words[0]?.global ?? -1
    expect(seqForSpoken(wordBlocks, spoken)).toBe(3)
  })

  it('skips the visible chapter when choosing the next offscreen measure', () => {
    expect(nextUnmeasuredChapter(2, [3, undefined], 0)).toBe(1)
    expect(nextUnmeasuredChapter(2, [undefined, undefined], 0)).toBe(1)
    expect(nextUnmeasuredChapter(2, [3, 2], 0)).toBe(-1)
  })
})
