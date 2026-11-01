import { describe, expect, it } from 'vitest'
import type { Block } from './readerContent'
import { buildNarration } from './readerContent'
import {
  chapterIndexForSeq,
  columnCountFromExtent,
  globalSpread,
  locateSpread,
  nextUnmeasuredChapter,
  seqForSpoken,
  splitReaderChapters,
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
