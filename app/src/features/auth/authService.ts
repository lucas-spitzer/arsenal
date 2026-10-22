import type { Session } from '@supabase/supabase-js'
import { apiRequestVoid } from '../../lib/apiClient'
import { authCallbackUrl, redirectToCanonicalHost } from './canonicalHost'
import { supabase } from '../../lib/supabaseClient'

// Refresh a little early so a request does not leave with a token that expires in flight.
const EXPIRY_SKEW_SECONDS = 60

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

async function readSessionToken(): Promise<string | null> {
  const { data, error } = await supabase.auth.getSession()

  if (error) {
    throw error
  }

  rememberSession(data.session)
  return data.session?.access_token ?? null
}
