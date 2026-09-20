import { describe, expect, it } from 'vitest'
import {
  READER_DEFINE_MAX_WORDS,
  buildNarration,
  buildNarrationClips,
  endsSentence,
  matchWikiTerms,
  resolveReaderSelection,
  timingIndexAt,
  type Block,
} from './readerContent'

function para(seq: number, id: string, text: string): Block {
  return {
    seq,
    id,
    kind: 'paragraph',
    level: 0,
    text,
    md: null,
    chapterTitle: 'Chapter',
    isChapterStart: false,
  }
}

const blocks: Block[] = [
  {
    seq: 0,
    id: 'h1',
    kind: 'heading',
    level: 1,
    text: 'Chapter',
    md: null,
    chapterTitle: 'Chapter',
    isChapterStart: true,
  },
  {
    seq: 1,
    id: 'p1',
    kind: 'paragraph',
    level: 0,
    text: 'Alpha beta gamma delta.',
    md: null,
    chapterTitle: 'Chapter',
    isChapterStart: false,
  },
  {
    seq: 2,
    id: 'p2',
    kind: 'paragraph',
    level: 0,
    text: 'They increased tempo in the fight.',
    md: null,
    chapterTitle: 'Chapter',
    isChapterStart: false,
  },
  {
    seq: 3,
    id: 'p3',
    kind: 'paragraph',
    level: 0,
    text: 'Later they slowed down.',
    md: null,
    chapterTitle: 'Chapter',
    isChapterStart: false,
  },
]

describe('resolveReaderSelection', () => {
  const { wordBlocks } = buildNarration(blocks)

  it('returns neighbors and sentence for a same-block selection', () => {
    const tempo = wordBlocks[2].words.find((w) => w.text === 'tempo')
    expect(tempo).toBeTruthy()
    const resolved = resolveReaderSelection(wordBlocks, [tempo!.global], new Map())
    expect(resolved).not.toBeNull()
    expect(resolved!.term).toBe('tempo')
    expect(resolved!.neighbors.prev).toBe('Alpha beta gamma delta.')
    expect(resolved!.neighbors.current).toBe('They increased tempo in the fight.')
    expect(resolved!.neighbors.next).toBe('Later they slowed down.')
    expect(resolved!.sentence).toBe('They increased tempo in the fight.')
    expect(resolved!.entryId).toBeNull()
  })

  it('rejects selections over the word cap', () => {
    const long: Block[] = [
      {
        seq: 0,
        id: 'long',
        kind: 'paragraph',
        level: 0,
        text: 'one two three four five six seven eight nine ten',
        md: null,
        chapterTitle: 'Chapter',
        isChapterStart: false,
      },
    ]
    const { wordBlocks: longBlocks } = buildNarration(long)
    const globals = longBlocks[0].words.map((w) => w.global)
    expect(globals.length).toBeGreaterThan(READER_DEFINE_MAX_WORDS)
    expect(
      resolveReaderSelection(longBlocks, globals.slice(0, READER_DEFINE_MAX_WORDS + 1), new Map()),
    ).toBeNull()
    expect(
      resolveReaderSelection(longBlocks, globals.slice(0, READER_DEFINE_MAX_WORDS), new Map())
        ?.term,
    ).toBe('one two three four five six seven eight')
  })

  it('rejects multi-block selections', () => {
    const a = wordBlocks[1].words[0].global
    const b = wordBlocks[2].words[0].global
    // Non-contiguous across blocks
    expect(resolveReaderSelection(wordBlocks, [a, b], new Map())).toBeNull()
  })

  it('returns wiki entryId when selection matches a linked term', () => {
    const entries = [
      { id: 'e1', preferred_label: 'tempo', aliases: [] as string[], status: 'canonical' },
    ]
    const termByWord = matchWikiTerms(wordBlocks, entries)
    const tempo = wordBlocks[2].words.find((w) => w.text === 'tempo')!
    expect(termByWord.get(tempo.global)).toBe('e1')
    const resolved = resolveReaderSelection(wordBlocks, [tempo.global], termByWord)
    expect(resolved!.entryId).toBe('e1')
  })
})

describe('endsSentence', () => {
  it('recognizes plain terminators and closers after them', () => {
    expect(endsSentence('combat.')).toBe(true)
    expect(endsSentence('right.”')).toBe(true)
    expect(endsSentence('Go."')).toBe(true)
    expect(endsSentence('looking!”')).toBe(true)
    expect(endsSentence('why?”')).toBe(true)
    expect(endsSentence('end.)')).toBe(true)
    expect(endsSentence('looking')).toBe(false)
    expect(endsSentence('Mr.')).toBe(true) // conservative; abbreviations still terminate
  })
})

describe('buildNarration', () => {
  it('keeps quoted epigraphs from sharing a sentence id with the next body paragraph', () => {
    const { wordBlocks } = buildNarration([
      para(0, 'q1', 'Hit the other fellow as hard as you can, when he ain’t looking.”'),
      para(1, 'q2', 'Hit the other fellow, as quick as you can.”'),
      para(2, 'body', 'This book is about winning in combat. Winning requires more.'),
    ])
    const quote1 = wordBlocks[0].words[0].sentence
    const quote2 = wordBlocks[1].words[0].sentence
    const bodyFirst = wordBlocks[2].words[0].sentence
    const bodySecond = wordBlocks[2].words.find((w) => w.text === 'Winning')!.sentence
    expect(quote1).not.toBe(quote2)
    expect(quote1).not.toBe(bodyFirst)
    expect(quote2).not.toBe(bodyFirst)
    expect(bodyFirst).not.toBe(bodySecond)
  })

  it('starts a new sentence after a closer-terminated token in the same paragraph', () => {
    const { wordBlocks } = buildNarration([para(0, 'p', 'Said “Go.” Then left.')])
    const go = wordBlocks[0].words.find((w) => w.text.endsWith('.”'))!
    const then = wordBlocks[0].words.find((w) => w.text === 'Then')!
    expect(go).toBeTruthy()
    expect(endsSentence(go.text)).toBe(true)
    expect(then.sentence).toBe(go.sentence + 1)
  })

  it('resets the sentence id at paragraph boundaries even without terminal punctuation', () => {
    const { wordBlocks } = buildNarration([
      para(0, 'a', 'No terminator here'),
      para(1, 'b', 'Next paragraph starts fresh'),
    ])
    expect(wordBlocks[0].words[0].sentence).not.toBe(wordBlocks[1].words[0].sentence)
  })
})

describe('buildNarrationClips', () => {
  it('groups paragraphs that share an audio_path into one clip', () => {
    const { wordBlocks } = buildNarration(blocks)
    const narration = new Map([
      [
        'p1',
        {
          id: 'n1',
          audio_path: 'chapter-0.mp3',
          alignment_source: 'provider' as const,
          words: [
            { s: 0, e: 0.2 },
            { s: 0.2, e: 0.4 },
            { s: 0.4, e: 0.6 },
            { s: 0.6, e: 0.8 },
          ],
        },
      ],
      [
        'p2',
        {
          id: 'n2',
          audio_path: 'chapter-0.mp3',
          alignment_source: 'provider' as const,
          words: [
            { s: 0.9, e: 1.1 },
            { s: 1.1, e: 1.3 },
            { s: 1.3, e: 1.5 },
            { s: 1.5, e: 1.7 },
            { s: 1.7, e: 1.9 },
            { s: 1.9, e: 2.1 },
          ],
        },
      ],
      [
        'p3',
        {
          id: 'n3',
          audio_path: 'chapter-1.mp3',
          alignment_source: 'provider' as const,
          words: [
            { s: 0, e: 0.2 },
            { s: 0.2, e: 0.4 },
            { s: 0.4, e: 0.6 },
            { s: 0.6, e: 0.8 },
          ],
        },
      ],
    ])
    const clips = buildNarrationClips(wordBlocks, narration)
    expect(clips).toHaveLength(2)
    expect(clips[0].audioKey).toBe('chapter-0.mp3')
    expect(clips[0].fetchNarrationId).toBe('n1')
    expect(clips[0].globals).toHaveLength(10)
    expect(clips[0].timings).toHaveLength(10)
    expect(clips[1].audioKey).toBe('chapter-1.mp3')
    expect(clips[1].globals).toHaveLength(4)
  })

  it('drops a paragraph whose timing count does not match rendered words', () => {
    const { wordBlocks } = buildNarration([para(0, 'p', 'one two three')])
    const narration = new Map([
      [
        'p',
        {
          id: 'n1',
          audio_path: 'clip.mp3',
          alignment_source: 'provider' as const,
          words: [
            { s: 0, e: 0.2 },
            { s: 0.2, e: 0.4 },
          ],
        },
      ],
    ])

    expect(buildNarrationClips(wordBlocks, narration)).toEqual([])
  })
})

describe('timingIndexAt', () => {
  const timings = [
    { s: 0.1, e: 0.18 },
    { s: 0.18, e: 0.24 },
    { s: 0.24, e: 0.31 },
  ]

  it('resolves short consecutive words from exact media time', () => {
    expect(timingIndexAt(timings, 0.099)).toBe(-1)
    expect(timingIndexAt(timings, 0.12)).toBe(0)
    expect(timingIndexAt(timings, 0.2)).toBe(1)
    expect(timingIndexAt(timings, 0.3)).toBe(2)
  })
})
