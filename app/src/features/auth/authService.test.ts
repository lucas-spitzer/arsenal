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
import { getAccessToken, rememberSession } from './authService'

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
})
