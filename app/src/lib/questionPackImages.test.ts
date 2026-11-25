import { describe, expect, it } from 'vitest'
import { imageStatus, mergeImages, questionImageNames } from './questionPackImages'

describe('questionImageNames', () => {
  it('reads string and object images once each', () => {
    const json = JSON.stringify({
      questions: [
        { question: 'A', image: 'Fireteam.png' },
        { question: 'B', image: { filename: ' Squad.jpg ', alt: 'squad' } },
        { question: 'C' },
        { question: 'D', image: 'Fireteam.png' },
        { question: 'E', image: '' },
      ],
    })
    expect(questionImageNames(json)).toEqual(['Fireteam.png', 'Squad.jpg'])
  })

  it('names nothing for unreadable JSON or a pack without questions', () => {
    expect(questionImageNames('{not json')).toEqual([])
    expect(questionImageNames(JSON.stringify({ terms: [] }))).toEqual([])
    expect(questionImageNames('[]')).toEqual([])
  })
})

describe('imageStatus', () => {
  it('splits attached, missing, and unused names', () => {
    const status = imageStatus(['a.png', 'b.png'], [{ name: 'a.png' }, { name: 'extra.png' }])
    expect(status).toEqual({ attached: ['a.png'], missing: ['b.png'], unused: ['extra.png'] })
  })
})

describe('mergeImages', () => {
  it('replaces same-name files and stops at the limit', () => {
    const current = [{ name: 'a.png', v: 1 }, { name: 'b.png', v: 1 }]
    const added = [{ name: 'a.png', v: 2 }, { name: 'c.png', v: 1 }, { name: 'd.png', v: 1 }]
    const { files, dropped } = mergeImages(current, added, 3)
    expect(files).toEqual([{ name: 'a.png', v: 2 }, { name: 'b.png', v: 1 }, { name: 'c.png', v: 1 }])
    expect(dropped).toBe(1)
  })
})
