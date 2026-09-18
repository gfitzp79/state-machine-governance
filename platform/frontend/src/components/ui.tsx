import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { cx, tone, label } from '../lib/format'

/* -------------------------------------------------------------- primitives */

export function Badge({
  value,
  children,
  className,
}: {
  value?: string | null
  children?: ReactNode
  className?: string
}) {
  return (
    <span className={cx('chip', tone(value), className)}>{children ?? label(value)}</span>
  )
}

export function Card({
  title,
  subtitle,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={cx('card overflow-hidden', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={cx('px-5 py-4', bodyClassName)}>{children}</div>
    </section>
  )
}

export function Stat({
  label: text,
  value,
  hint,
  tone: t,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'default' | 'warn' | 'bad' | 'good'
}) {
  const colour =
    t === 'bad'
      ? 'text-rose-600 dark:text-rose-400'
      : t === 'warn'
        ? 'text-amber-600 dark:text-amber-400'
        : t === 'good'
          ? 'text-emerald-600 dark:text-emerald-400'
          : 'text-ink'
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        {text}
      </div>
      <div className={cx('mt-1 text-2xl font-semibold tabular-nums', colour)}>{value}</div>
      {hint && <div className="mt-0.5 truncate text-xs text-ink-faint">{hint}</div>}
    </div>
  )
}

export function Field({
  label: text,
  hint,
  children,
  className,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={className}>
      <label className="label">{text}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </div>
  )
}

export function Detail({ label: text, children }: { label: string; children: ReactNode }) {
  return (
    <div className="py-2">
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        {text}
      </dt>
      <dd className="mt-1 text-sm text-ink">{children ?? '—'}</dd>
    </div>
  )
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-4 py-10 text-center">
      <p className="text-sm font-medium text-ink-muted">{title}</p>
      {hint && <p className="max-w-md text-xs text-ink-faint">{hint}</p>}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx('h-4 w-4 animate-spin', className)} />
}

export function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center text-ink-faint">
      <Spinner className="h-6 w-6" />
    </div>
  )
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm sm:p-8">
      <div
        className={cx(
          'card my-auto w-full animate-fade-in shadow-pop',
          wide ? 'max-w-3xl' : 'max-w-lg',
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            {description && <p className="mt-1 text-xs text-ink-muted">{description}</p>}
          </div>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  )
}

export function Table({
  columns,
  children,
  className,
}: {
  columns: ReactNode[]
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cx('overflow-x-auto', className)}>
      <table className="w-full border-collapse">
        <thead className="border-b bg-surface-sunken">
          <tr>
            {columns.map((c, i) => (
              <th key={i} className="table-head whitespace-nowrap">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">{children}</tbody>
      </table>
    </div>
  )
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; count?: number }[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            'relative whitespace-nowrap px-3 py-2.5 text-sm font-medium transition-colors',
            active === t.id
              ? 'text-accent'
              : 'text-ink-muted hover:text-ink',
          )}
        >
          {t.label}
          {t.count !== undefined && (
            <span className="ml-1.5 rounded bg-surface-sunken px-1.5 py-0.5 text-[11px] tabular-nums text-ink-muted">
              {t.count}
            </span>
          )}
          {active === t.id && (
            <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" />
          )}
        </button>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ toasts */

type Toast = { id: number; kind: 'ok' | 'error' | 'info'; title: string; body?: string; rule?: string }

const ToastContext = createContext<{
  push: (t: Omit<Toast, 'id'>) => void
}>({ push: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { ...t, id }])
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), t.kind === 'error' ? 9000 : 4500)
  }, [])

  const value = useMemo(() => ({ push }), [push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              'pointer-events-auto card animate-fade-in border-l-4 px-4 py-3 shadow-pop',
              t.kind === 'ok'
                ? 'border-l-emerald-500'
                : t.kind === 'error'
                  ? 'border-l-rose-500'
                  : 'border-l-sky-500',
            )}
          >
            <div className="flex items-start gap-2.5">
              {t.kind === 'ok' ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              ) : t.kind === 'error' ? (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
              ) : (
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-500" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{t.title}</p>
                {t.rule && (
                  <p className="mono mt-1 inline-block rounded bg-surface-sunken px-1.5 py-0.5 text-ink-muted">
                    {t.rule}
                  </p>
                )}
                {t.body && <p className="mt-1 text-xs leading-relaxed text-ink-muted">{t.body}</p>}
              </div>
              <button
                className="text-ink-faint hover:text-ink"
                onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
