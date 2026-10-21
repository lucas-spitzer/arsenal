const CANONICAL_ORIGIN = 'https://www.atlas3.app'

function isLoopbackHost(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1'
}

export function authCallbackUrl(): string {
  if (isLoopbackHost(window.location.hostname)) {
    return `${window.location.origin}/auth/callback`
  }
  return `${CANONICAL_ORIGIN}/auth/callback`
}

// The saved session lives in localStorage for one origin. Move to Atlas
// before Supabase writes that storage, so a later visit to the student URL
// finds it. Returns true when the browser is leaving this page.
export function redirectToCanonicalHost(): boolean {
  if (isLoopbackHost(window.location.hostname)) return false
  if (window.location.origin === CANONICAL_ORIGIN) return false

  window.location.replace(
    `${CANONICAL_ORIGIN}${window.location.pathname}${window.location.search}${window.location.hash}`,
  )
  return true
}
