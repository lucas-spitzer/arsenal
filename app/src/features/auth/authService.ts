import type { Session } from '@supabase/supabase-js'
import { apiRequestVoid } from '../../lib/apiClient'
import { authCallbackUrl, redirectToCanonicalHost } from './canonicalHost'
import { supabase } from '../../lib/supabaseClient'

// Refresh a little early so a request does not leave with a token that expires in flight.
const EXPIRY_SKEW_SECONDS = 60
// A tab frozen mid-refresh can hold the auth lock until its timers resume.
// Bound the wait so the reader can fail and retry instead of spinning.
export const SESSION_LOOKUP_TIMEOUT_MS = 8_000

export class SessionLookupTimeoutError extends Error {
  constructor() {
    super('Session lookup timed out.')
    this.name = 'SessionLookupTimeoutError'
  }
}

function isSessionLookupTimeout(error: unknown): boolean {
  return error instanceof SessionLookupTimeoutError
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new SessionLookupTimeoutError()), ms)
    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error: unknown) => {
        clearTimeout(timer)
        reject(error)
      },
    )
  })
}

type CachedToken = {
  token: string
  expiresAt: number
}

let cached: CachedToken | null = null
let pendingSession: Promise<string | null> | null = null

export function rememberSession(session: Session | null): void {
  const expiresAt = session?.expires_at
  if (!session?.access_token || typeof expiresAt !== 'number') {
    cached = null
    return
  }
  cached = { token: session.access_token, expiresAt }
}

function cachedAccessToken(nowSeconds = Math.floor(Date.now() / 1000)): string | null {
  if (!cached) return null
  if (cached.expiresAt - EXPIRY_SKEW_SECONDS <= nowSeconds) return null
  return cached.token
}

export async function signInWithGoogle(): Promise<void> {
  if (redirectToCanonicalHost()) return

  const { error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: authCallbackUrl(),
    },
  })

  if (error) {
    throw error
  }
}

export async function requestEmailCode(email: string): Promise<void> {
  if (redirectToCanonicalHost()) return

  await apiRequestVoid('/auth/email-code', {
    method: 'POST',
    requiresAuth: false,
    body: JSON.stringify({ email }),
  })
}

export async function verifyEmailCode(email: string, token: string): Promise<void> {
  if (redirectToCanonicalHost()) return

  const { error } = await supabase.auth.verifyOtp({
    email,
    token,
    type: 'email',
  })

  if (error) {
    throw error
  }
}

export async function signOut(): Promise<void> {
  const { error } = await supabase.auth.signOut()

  if (error) {
    throw error
  }
}

export async function getAccessToken(): Promise<string | null> {
  const token = cachedAccessToken()
  if (token) return token

  // getSession takes an exclusive lock. Parallel library calls share one read.
  if (!pendingSession) {
    pendingSession = readSessionToken().finally(() => {
      pendingSession = null
    })
  }
  return pendingSession
}

async function readSessionOnce(): Promise<string | null> {
  const { data, error } = await withTimeout(
    supabase.auth.getSession(),
    SESSION_LOOKUP_TIMEOUT_MS,
  )

  if (error) {
    throw error
  }

  rememberSession(data.session)
  return data.session?.access_token ?? null
}

async function readSessionToken(): Promise<string | null> {
  try {
    return await readSessionOnce()
  } catch (error: unknown) {
    if (!isSessionLookupTimeout(error)) throw error
    return await readSessionOnce()
  }
}
