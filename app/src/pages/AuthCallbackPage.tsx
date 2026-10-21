import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArsenalMark } from '../components/brand/ArsenalMark'
import { redirectToCanonicalHost } from '../features/auth/canonicalHost'
import { supabase } from '../lib/supabaseClient'
import '../gate.css'

export function AuthCallbackPage() {
  const navigate = useNavigate()
  const [message, setMessage] = useState('Completing secure login.')

  useEffect(() => {
    async function handleCallback() {
      if (redirectToCanonicalHost()) return

      const params = new URLSearchParams(window.location.search)
      const code = params.get('code')

      const { error } = code
        ? await supabase.auth.exchangeCodeForSession(code)
        : await supabase.auth.getSession()

      if (error) {
        console.error('Authentication callback failed:', error.message)
        setMessage('Authentication failed. Returning to login.')
        navigate('/login', { replace: true })
        return
      }

      navigate('/app', { replace: true })
    }

    void handleCallback()
  }, [navigate])

  return (
    <main className="as-gate" aria-live="polite">
      <section className="as-gate__status">
        <ArsenalMark className="as-gate__mark" />
        <p className="as-gate__eyebrow">Secure Login</p>
        <p className="as-gate__status-msg">{message}</p>
        <div className="as-gate__scanner" aria-hidden="true" />
      </section>
    </main>
  )
}
