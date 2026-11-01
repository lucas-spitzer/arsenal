import { describe, expect, it } from 'vitest'
import { settleQuietRecheck } from './approvalRecheck'

describe('settleQuietRecheck', () => {
  it('keeps an approved session when a quiet recheck fails for a reason other than 401 or 403', () => {
    expect(settleQuietRecheck(true, null)).toEqual({ kind: 'keep-approved' })
    expect(settleQuietRecheck(true, 500)).toEqual({ kind: 'keep-approved' })
  })

  it('rejects the session on 401 and 403 even during a quiet recheck', () => {
    expect(settleQuietRecheck(true, 401)).toEqual({ kind: 'rejected' })
    expect(settleQuietRecheck(false, 403)).toEqual({ kind: 'rejected' })
  })

  it('marks a first check unavailable when the failure is not an auth rejection', () => {
    expect(settleQuietRecheck(false, 500)).toEqual({ kind: 'unavailable' })
    expect(settleQuietRecheck(false, null)).toEqual({ kind: 'unavailable' })
  })
})
