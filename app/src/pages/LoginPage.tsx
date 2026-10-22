import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { ArsenalMark } from '../components/brand/ArsenalMark'
import { ApiError } from '../lib/apiClient'
import { requestEmailCode, signInWithGoogle, signOut, verifyEmailCode } from '../features/auth/authService'
import { useAuth } from '../features/auth/authContext'
import '../gate.css'

interface LocationState {
  from?: {
    pathname?: string
  }
}

const EMAIL_CODE_LENGTH = 8

function arrivedSignIn(params: URLSearchParams): { email: string; code: string } | null {
  const code = (params.get('code') ?? '').replace(/\D/g, '')
  const email = (params.get('email') ?? '').trim()
  if (code.length !== EMAIL_CODE_LENGTH) return null
  if (
    email.length < 3 ||
    email.length > 320 ||
    !email.includes('@') ||
    email.startsWith('@') ||
    email.endsWith('@') ||
    /\s/.test(email)
  ) {
    return null
  }
  return { email, code }
}

const systemModules = [
  {
    name: 'Intellex',
    tag: 'Knowledge Base',
    description:
      'Ingests and deconstructs source documents into a structured, source-grounded knowledge base.',
  },
  {
    name: 'Mathesys',
    tag: 'Generation',
    description:
      'Produces narration scripts, audio, and educational artifacts from Intellex output.',
  },
  {
    name: 'QnGen',
    tag: 'Assessment',
    description:
      'Builds flashcard, question, and scenario sets that test every production run.',
  },
]

export function LoginPage() {
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const arrived = useState(() => arrivedSignIn(searchParams))[0]
  const { approvalError, approvalStatus, isAuthenticated, isLoading } = useAuth()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [pending, setPending] = useState<'google' | 'code' | null>(null)
  const [email, setEmail] = useState(arrived?.email ?? '')
  const [code, setCode] = useState(arrived?.code ?? '')
  const [codeSentTo, setCodeSentTo] = useState<string | null>(arrived?.email ?? null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!arrived) return
    let cancelled = false
    void navigator.clipboard.writeText(arrived.code).then(
      () => {
        if (!cancelled) setCopied(true)
      },
      () => undefined,
    )
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('code')
        next.delete('email')
        return next
      },
      { replace: true },
    )
    return () => {
      cancelled = true
    }
  }, [arrived, setSearchParams])

  const fromPath = (location.state as LocationState | null)?.from?.pathname ?? '/app'

  if (!isLoading && isAuthenticated && approvalStatus !== 'rejected') {
    return <Navigate to={fromPath} replace />
  }

  async function handleGoogleLogin() {
    try {
      setPending('google')
      setErrorMessage(null)
      await signInWithGoogle()
    } catch (error) {
      console.error(
        'Unable to start Google login:',
        error instanceof Error ? error.message : error,
      )
      setErrorMessage('Unable to start Google login. Try again.')
      setPending(null)
    }
  }

  async function handleSignOut() {
    await signOut()
  }

  async function handleRequestCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const address = email.trim()
    if (!address) return

    try {
      setPending('code')
      setErrorMessage(null)
      await requestEmailCode(address)
      setEmail(address)
      setCode('')
      setCodeSentTo(address)
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError
          ? error.message
          : 'Unable to send a sign-in code. Try again.',
      )
    } finally {
      setPending(null)
    }
  }

  async function handleVerifyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!codeSentTo || code.length !== EMAIL_CODE_LENGTH) return

    try {
      setPending('code')
      setErrorMessage(null)
      await verifyEmailCode(codeSentTo, code)
    } catch (error) {
      console.error(
        'Unable to verify sign-in code:',
        error instanceof Error ? error.message : error,
      )
      setErrorMessage('That code is not valid. Request another and try again.')
    } finally {
      setPending(null)
    }
  }

  async function handleResendCode() {
    if (!codeSentTo) return

    try {
      setPending('code')
      setErrorMessage(null)
      await requestEmailCode(codeSentTo)
      setCode('')
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError
          ? error.message
          : 'Unable to send a sign-in code. Try again.',
      )
    } finally {
      setPending(null)
    }
  }

  return (
    <main className="as-gate">
      <div className="as-gate__login">
        <section className="as-gate__brand" aria-label="About Arsenal">
          <div className="as-gate__brand-head">
            <ArsenalMark className="as-gate__mark" />
            <div>
              <div className="as-gate__wordmark">Arsenal</div>
              <div className="as-gate__tagline">Arsenal Education Platform</div>
            </div>
          </div>

          <ol className="as-gate__modules">
            {systemModules.map((module, index) => (
              <li
                key={module.name}
                className="as-gate__module"
                style={{ '--i': index } as CSSProperties}
              >
                <span className="as-gate__module-dot">{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <div className="as-gate__module-name">
                    {module.name}
                    <span className="as-gate__module-tag">{module.tag}</span>
                  </div>
                  <p>{module.description}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="as-gate__sysline">
            <span className="as-gate__livedot" aria-hidden="true" />
            Systems nominal · Intellex / Mathesys / QnGen
          </div>
        </section>

        <section className="as-gate__panel" aria-labelledby="auth-title">
          <p className="as-gate__eyebrow">Access Restricted</p>
          <h1 id="auth-title">Operator Sign-In</h1>
          <p className="as-gate__copy">
            Arsenal is a private production environment. Access is restricted to approved
            accounts.
          </p>

          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={pending !== null || isLoading}
            className="as-gate__cta"
          >
            {pending === 'google' ? 'Redirecting…' : 'Continue with Google'}
          </button>

          <p className="as-gate__or">or</p>

          {codeSentTo ? (
            <form className="as-gate__email" onSubmit={(event) => void handleVerifyCode(event)}>
              <label className="as-gate__label" htmlFor="sign-in-code">
                Sign-in code
              </label>
              <input
                id="sign-in-code"
                className="as-gate__input as-gate__input--code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={EMAIL_CODE_LENGTH}
                value={code}
                onChange={(event) =>
                  setCode(event.target.value.replace(/\D/g, '').slice(0, EMAIL_CODE_LENGTH))
                }
                required
              />
              <p className="as-gate__helper">
                {copied
                  ? 'Copied to the clipboard. It expires shortly and works once.'
                  : `Enter the 8-digit code sent to ${codeSentTo}. It expires shortly and works once.`}
              </p>
              <button
                type="submit"
                className="as-gate__cta"
                disabled={pending !== null || isLoading || code.length !== EMAIL_CODE_LENGTH}
              >
                {pending === 'code' ? 'Checking…' : 'Sign in'}
              </button>
              <button
                type="button"
                className="as-gate__text-action"
                disabled={pending !== null || isLoading}
                onClick={() => void handleResendCode()}
              >
                Email another code
              </button>
              <button
                type="button"
                className="as-gate__text-action"
                disabled={pending !== null || isLoading}
                onClick={() => {
                  setCodeSentTo(null)
                  setCode('')
                  setErrorMessage(null)
                }}
              >
                Use a different email
              </button>
            </form>
          ) : (
            <form className="as-gate__email" onSubmit={(event) => void handleRequestCode(event)}>
              <label className="as-gate__label" htmlFor="sign-in-email">
                Email
              </label>
              <input
                id="sign-in-email"
                className="as-gate__input"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
              <button
                type="submit"
                className="as-gate__cta"
                disabled={pending !== null || isLoading || !email.trim()}
              >
                {pending === 'code' ? 'Sending…' : 'Email me a code'}
              </button>
            </form>
          )}

          <p className="as-gate__helper">Approved accounts may sign in with Google or an email code.</p>

          {approvalStatus === 'rejected' ? (
            <div className="as-gate__error" role="alert">
              <p>{approvalError ?? 'This account is not approved for Arsenal access.'}</p>
              <button type="button" className="as-gate__inline-action" onClick={handleSignOut}>
                Sign out
              </button>
            </div>
          ) : null}

          {errorMessage ? (
            <div className="as-gate__error" role="alert">
              <p>{errorMessage}</p>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  )
}
