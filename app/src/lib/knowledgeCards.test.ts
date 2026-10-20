import { describe, expect, it } from 'vitest'

import { definitionCardBack, listCardBack } from './knowledgeCards'

describe('list card backs', () => {
  it('numbers item names and leaves the overview off', () => {
    const entry = {
      entry_kind: 'list',
      definition: 'The foundational pillars of a profession.',
      items: [
        { name: 'Special Expertise', details: 'Mastery of a specialized body of knowledge.' },
        { name: 'Responsibility to Society' },
        { name: ' Corporateness ' },
        { name: 'Professional Ethic and Ethos' },
      ],
    }

    expect(listCardBack(entry)).toBe(
      [
        '1. Special Expertise',
        '2. Responsibility to Society',
        '3. Corporateness',
        '4. Professional Ethic and Ethos',
      ].join('\n'),
    )
    expect(definitionCardBack(entry)).toBe(listCardBack(entry))
  })

  it('keeps a term back as the definition', () => {
    expect(
      definitionCardBack({
        entry_kind: 'term',
        definition: 'The institutional role of commissioned officers to preserve the profession.',
        items: [{ name: 'Not on the card' }],
      }),
    ).toBe('The institutional role of commissioned officers to preserve the profession.')
  })

  it('falls back to the overview when a list has no names', () => {
    expect(listCardBack({ entry_kind: 'list', definition: 'The forms.', items: [] })).toBe('The forms.')
  })
})
