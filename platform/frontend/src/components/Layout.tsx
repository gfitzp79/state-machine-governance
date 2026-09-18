import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Bell,
  Boxes,
  Cpu,
  FileText,
  Gauge,
  LogOut,
  Menu,
  Moon,
  ScrollText,
  ShieldAlert,
  Sun,
  Target,
  Wrench,
  X,
} from 'lucide-react'
import { api, clearSession, getStoredUser } from '../lib/api'
import { orgInitials, useConfig } from '../lib/config'
import { cx, initials } from '../lib/format'
import { Badge } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: Gauge, end: true },
  { to: '/risks', label: 'Risks', icon: ShieldAlert },
  { to: '/controls', label: 'Controls', icon: Boxes },
  { to: '/policies', label: 'Policies', icon: FileText },
  { to: '/treatments', label: 'Treatments', icon: Wrench },
  { to: '/threat-models', label: 'Threat models', icon: Target },
  { to: '/engine', label: 'Engine', icon: Cpu },
  { to: '/audit', label: 'Audit trail', icon: ScrollText },
]

function useTheme() {
  const [dark, setDark] = useState(() =>
    typeof document !== 'undefined' ? document.documentElement.classList.contains('dark') : false,
  )
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try {
      localStorage.setItem('smg-theme', dark ? 'dark' : 'light')
    } catch {
      /* ignore */
    }
  }, [dark])
  return { dark, toggle: () => setDark((d) => !d) }
}

export default function Layout() {
  const navigate = useNavigate()
  const user = getStoredUser()
  const config = useConfig()
  const { dark, toggle } = useTheme()
  const [navOpen, setNavOpen] = useState(false)
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      api
        .get<unknown[]>('/notifications?unread_only=true')
        .then((rows) => !cancelled && setUnread(rows.length))
        .catch(() => undefined)
    load()
    const timer = setInterval(load, 60_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const signOut = () => {
    clearSession()
    navigate('/login')
  }

  return (
    <div className="flex min-h-full">
      {/* sidebar */}
      <aside
        className={cx(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r bg-surface-raised transition-transform lg:static lg:translate-x-0',
          navOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center gap-2.5 border-b px-5 py-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-sm font-bold text-white">
            {orgInitials(config?.organisation.name)}
          </div>
          <div className="min-w-0">
            <p
              className="truncate text-sm font-semibold leading-tight text-ink"
              title={config?.organisation.name}
            >
              {config?.organisation.name ?? 'State Machine Governance'}
            </p>
            <p className="truncate text-xs text-ink-muted">
              {config?.organisation.tagline ?? 'Governance platform'}
            </p>
          </div>
          <button
            className="ml-auto text-ink-faint lg:hidden"
            onClick={() => setNavOpen(false)}
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {NAV.map(({ to, label: text, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setNavOpen(false)}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-accent-soft text-accent'
                    : 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {text}
            </NavLink>
          ))}
        </nav>

        <div className="border-t p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-xs font-semibold text-ink-muted">
              {initials(user?.full_name)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{user?.full_name}</p>
              <p className="truncate text-xs text-ink-faint">{user?.job_title}</p>
            </div>
            <button
              className="text-ink-faint hover:text-ink"
              onClick={signOut}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1 px-2">
            {(user?.roles ?? []).slice(0, 4).map((r) => (
              <span
                key={r}
                className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] font-medium text-ink-muted"
              >
                {r.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      </aside>

      {navOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}

      {/* main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b bg-surface/85 px-4 py-3 backdrop-blur sm:px-6">
          <button
            className="text-ink-muted lg:hidden"
            onClick={() => setNavOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="ml-auto flex items-center gap-2">
            <NavLink
              to="/notifications"
              className="relative rounded-lg border bg-surface-raised p-2 text-ink-muted hover:text-ink"
              aria-label="Notifications"
            >
              <Bell className="h-4 w-4" />
              {unread > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
                  {unread > 9 ? '9+' : unread}
                </span>
              )}
            </NavLink>
            <button
              className="rounded-lg border bg-surface-raised p-2 text-ink-muted hover:text-ink"
              onClick={toggle}
              aria-label="Toggle theme"
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-[1400px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: React.ReactNode
  meta?: React.ReactNode
}) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <p className="mono mb-1 text-ink-faint">{eyebrow}</p>
          )}
          <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
          {description && (
            <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-muted">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
      {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
    </div>
  )
}

export { Badge }
