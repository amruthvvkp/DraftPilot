import { FormEvent, ReactNode, useEffect, useState } from 'react'
import { AUTH_REQUIRED_EVENT, getAuthStatus, signIn } from './api'

type GateState = 'checking' | 'open' | 'locked'

/** Render children once the API is reachable, asking for the API token when one is configured. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>('checking')
  const [token, setToken] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getAuthStatus()
      .then(status => setState(!status.auth_required || status.authenticated ? 'open' : 'locked'))
      .catch(() => setState('open'))
    const lock = () => setState('locked')
    window.addEventListener(AUTH_REQUIRED_EVENT, lock)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, lock)
  }, [])

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setError('')
    try {
      await signIn(token)
      setToken('')
      window.location.reload()
    } catch {
      setError('That token was not accepted.')
    }
  }

  if (state === 'checking') return null
  if (state === 'open') return <>{children}</>
  return <main className="signin-shell"><form className="signin-card" onSubmit={event => void submit(event)} aria-labelledby="signin-title">
    <span className="brand-mark">✦</span>
    <h1 id="signin-title">Sign in to DraftPilot</h1>
    <p>This studio is protected by an API token (<code>API__TOKEN</code>).</p>
    <label>API token<input type="password" autoComplete="current-password" value={token} onChange={event => setToken(event.target.value)} autoFocus required /></label>
    {error && <p role="alert" className="signin-error">{error}</p>}
    <button className="button primary" type="submit">Sign in</button>
  </form></main>
}
