export type QuietRecheck =
  | { kind: 'rejected' }
  | { kind: 'keep-approved' }
  | { kind: 'unavailable' }

/**
 * A tab-focus token refresh re-runs the approval check. A network blip on that
 * quiet pass must not clear the approved flag, or the next event replaces the
 * app with the security scanner. 401 and 403 still end the session.
 */
export function settleQuietRecheck(quiet: boolean, status: number | null): QuietRecheck {
  if (status === 401 || status === 403) return { kind: 'rejected' }
  if (quiet) return { kind: 'keep-approved' }
  return { kind: 'unavailable' }
}
