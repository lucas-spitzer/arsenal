import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { ApiError, getCurrentUser, hasApiBaseUrl } from '../../lib/apiClient'
import type { CurrentUserResponse } from '../../lib/apiClient'
import { supabase } from '../../lib/supabaseClient'
import { rememberSession } from './authService'
import { AuthContext } from './authContext'
import type { ApprovalStatus, AuthContextValue } from './authContext'

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [session, setSession] = useState<Session | null>(null)
  const [isSessionLoading, setIsSessionLoading] = useState(true)
  const [approvalStatus, setApprovalStatus] = useState<ApprovalStatus>('idle')
  const [approvalError, setApprovalError] = useState<string | null>(null)
  const [approvedUser, setApprovedUser] = useState<CurrentUserResponse | null>(null)
  // Keep the protected tree mounted across token refreshes (tab focus often
  // re-fires onAuthStateChange). Only the first approval check should gate UI.
  const wasApprovedRef = useRef(false)

  useEffect(() => {
    // INITIAL_SESSION is included. A parallel getSession() can refresh the
    // same token twice and revoke the saved login.
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      rememberSession(nextSession)
      setSession(nextSession)
      setIsSessionLoading(false)
    })

    return () => {
      listener.subscription.unsubscribe()
    }
  }, [])

  useEffect(() => {
    let isCurrent = true

    async function verifyApproval() {
      if (!session) {
        wasApprovedRef.current = false
        setApprovedUser(null)
        setApprovalError(null)
        setApprovalStatus('idle')
        return
      }

      if (!hasApiBaseUrl()) {
        wasApprovedRef.current = false
        setApprovedUser(null)
        setApprovalStatus('unavailable')
        setApprovalError('Set VITE_API_BASE_URL to enable the Arsenal approval check.')
        return
      }

      const quiet = wasApprovedRef.current
      if (!quiet) {
        setApprovedUser(null)
        setApprovalError(null)
        setApprovalStatus('checking')
      }

      try {
        const currentUser = await getCurrentUser()

        if (!isCurrent) return

        wasApprovedRef.current = true
        setApprovedUser(currentUser)
        setApprovalStatus('approved')
        setApprovalError(null)
      } catch (error) {
        if (!isCurrent) return

        wasApprovedRef.current = false

        if (error instanceof ApiError && error.status === 403) {
          setApprovedUser(null)
          setApprovalStatus('rejected')
          setApprovalError('This Google account is not approved for Arsenal access.')
          return
        }

        if (error instanceof ApiError && error.status === 401) {
          setApprovedUser(null)
          setApprovalStatus('rejected')
          setApprovalError('Your session could not be verified. Sign in again.')
          return
        }

        console.error(
          'Arsenal approval check failed:',
          error instanceof Error ? error.message : error,
        )
        // Keep an already-approved session usable if a transient network blip
        // hits during a quiet recheck (e.g. tab focus token refresh).
        if (quiet) return

        setApprovedUser(null)
        setApprovalStatus('unavailable')
        setApprovalError('Arsenal could not reach the approval service.')
      }
    }

    void verifyApproval()

    return () => {
      isCurrent = false
    }
  }, [session])

  const value = useMemo<AuthContextValue>(() => {
    return {
      approvalError,
      approvalStatus,
      approvedUser,
      isApproved: approvalStatus === 'approved',
      isAuthenticated: Boolean(session),
      isLoading: isSessionLoading || approvalStatus === 'checking',
      user: session?.user ?? null,
    }
  }, [approvalError, approvalStatus, approvedUser, isSessionLoading, session])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
