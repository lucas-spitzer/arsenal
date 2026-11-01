import type { Session } from '@supabase/supabase-js'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
    },
  },
}))

import { supabase } from '../../lib/supabaseClient'
import {
  getAccessToken,
  rememberSession,
  SESSION_LOOKUP_TIMEOUT_MS,
  SessionLookupTimeoutError,
} from './authService'

const getSession = vi.mocked(supabase.auth.getSession)

function session(token: string, expiresInSeconds: number): Session {
  return {
    access_token: token,
    refresh_token: 'refresh',
    expires_in: expiresInSeconds,
    expires_at: Math.floor(Date.now() / 1000) + expiresInSeconds,
    token_type: 'bearer',
    user: {
      id: 'user-1',
      app_metadata: {},
      user_metadata: {},
      aud: 'authenticated',
      created_at: '2026-01-01T00:00:00Z',
    },
  }
}

beforeEach(() => {
  rememberSession(null)
  getSession.mockReset()
})

describe('getAccessToken', () => {
  it('returns the listener token without calling getSession', async () => {
    rememberSession(session('cached', 3600))

    await expect(getAccessToken()).resolves.toBe('cached')
    expect(getSession).not.toHaveBeenCalled()
  })

  it('ignores a token that is about to expire', async () => {
    rememberSession(session('stale', 30))
    getSession.mockResolvedValue({
      data: { session: session('fresh', 3600) },
      error: null,
    })

    await expect(getAccessToken()).resolves.toBe('fresh')
    expect(getSession).toHaveBeenCalledOnce()
  })

  it('shares one getSession across parallel callers', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    getSession.mockImplementation(async () => {
      await gate
      return { data: { session: session('shared', 3600) }, error: null }
    })

    const first = getAccessToken()
    const second = getAccessToken()
    release()

    await expect(Promise.all([first, second])).resolves.toEqual(['shared', 'shared'])
    expect(getSession).toHaveBeenCalledOnce()
  })

  it('retries getSession once when the first lookup times out', async () => {
    vi.useFakeTimers()
    try {
      let calls = 0
      getSession.mockImplementation(
        () =>
          new Promise((resolve) => {
            calls += 1
            if (calls === 1) return
            resolve({ data: { session: session('fresh', 3600) }, error: null })
          }),
      )

      const pending = getAccessToken()
      await vi.advanceTimersByTimeAsync(SESSION_LOOKUP_TIMEOUT_MS)
      await expect(pending).resolves.toBe('fresh')
      expect(getSession).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('rejects when both session lookups time out', async () => {
    vi.useFakeTimers()
    try {
      getSession.mockImplementation(() => new Promise(() => {}))
      const pending = getAccessToken()
      const rejected = expect(pending).rejects.toBeInstanceOf(SessionLookupTimeoutError)
      await vi.advanceTimersByTimeAsync(SESSION_LOOKUP_TIMEOUT_MS * 2)
      await rejected
      expect(getSession).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
