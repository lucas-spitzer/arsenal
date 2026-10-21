import { apiRequestVoid } from '../../lib/apiClient'
import { authCallbackUrl, redirectToCanonicalHost } from './canonicalHost'
import { supabase } from '../../lib/supabaseClient'

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
  const { data, error } = await supabase.auth.getSession()

  if (error) {
    throw error
  }

  return data.session?.access_token ?? null
}
