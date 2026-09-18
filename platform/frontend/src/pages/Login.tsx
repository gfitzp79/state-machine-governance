import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { ApiError, getToken, login } from '../lib/api'
import { orgInitials, useConfig } from '../lib/config'
import { Field, Spinner } from '../components/ui'

const DEMO = [
  { email: 'analyst@example.com', who: 'Priya Raman', role: 'Risk Analyst' },
  { email: 'grc@example.com', who: 'Tomas Lindqvist', role: 'GRC Engineer' },
  { email: 'ciso@example.com', who: 'Marcus Bell', role: 'CISO' },
  { email: 'control@example.com', who: 'Jonah Weiss', role: 'Control Owner' },
  { email: 'appsec@example.com', who: 'Ines Ferreira', role: 'AppSec Lead' },
  { email: 'admin@example.com', who: 'Ada Okafor', role: 'Admin' },
]

export default function Login() {
  const navigate = useNavigate()
  const config = useConfig()
  const [email, setEmail] = useState('analyst@example.com')
  const [password, setPassword] = useState('changeme123')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (getToken()) {
    navigate('/', { replace: true })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-sm font-bold text-white">
              {orgInitials(config?.organisation.name)}
            </div>
            <div>
              <p className="text-sm font-semibold leading-tight text-ink">
                {config?.organisation.name ?? 'State Machine Governance'}
              </p>
              <p className="text-xs text-ink-muted">
                {config?.organisation.tagline ?? 'Governance platform'}
              </p>
            </div>
          </div>

          <h1 className="text-2xl font-semibold tracking-tight text-ink">Sign in</h1>
          <p className="mt-1.5 text-sm text-ink-muted">
            Your roles determine which lifecycle transitions you can fire.
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label="Email">
              <input
                className="field"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </Field>
            <Field label="Password">
              <input
                className="field"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>

            {error && (
              <p className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300">
                {error}
              </p>
            )}

            <button className="btn-primary w-full" disabled={busy}>
              {busy ? <Spinner /> : <ArrowRight className="h-4 w-4" />}
              Sign in
            </button>
          </form>

          <div className="mt-8 rounded-xl border bg-surface-sunken p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
              Demo accounts
            </p>
            <div className="space-y-1">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  onClick={() => {
                    setEmail(d.email)
                    setPassword('changeme123')
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-surface-raised"
                >
                  <span className="font-medium text-ink">{d.who}</span>
                  <span className="text-ink-faint">{d.role}</span>
                  <span className="mono ml-auto text-ink-faint">{d.email}</span>
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-ink-faint">
              Password for all demo accounts: <span className="mono">changeme123</span>
            </p>
          </div>
        </div>
      </div>

      <div className="hidden bg-surface-sunken lg:flex lg:items-center lg:justify-center lg:px-12">
        <div className="max-w-md">
          <h2 className="text-lg font-semibold text-ink">Governance is a state machine.</h2>
          <p className="mt-3 text-sm leading-relaxed text-ink-muted">
            Risks, controls, policies and threat models are interconnected entities whose state
            changes propagate. A policy describes intent. A tool built from a precise
            specification enforces it at the data layer.
          </p>
          <ul className="mt-6 space-y-3 text-sm text-ink-muted">
            {[
              'Every lifecycle transition is gated, and every gate names the rule that blocked it.',
              'Hard rules run as invariants before commit, on every write path.',
              'A control entering Failure re-locks residual scores and re-opens the threats it was mitigating.',
              'Audit and version history reject UPDATE and DELETE at the database layer.',
            ].map((line) => (
              <li key={line} className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                {line}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
