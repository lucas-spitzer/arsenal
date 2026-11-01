import { describe, expect, it } from 'vitest'
import { threadTitle } from './assistantApi'

describe('threadTitle', () => {
  it('keeps the first five words', () => {
    expect(
      threadTitle(
        'Explain the obligations of loyal subordination and how junior officers maintain forthright dialogue',
      ),
    ).toBe('Explain the obligations of loyal')
    expect(threadTitle('Patrol base')).toBe('Patrol base')
    expect(threadTitle('  Explain the commission.  ')).toBe('Explain the commission')
  })
})
