import { useEffect, useMemo, useState } from 'react'
import { Check, Search, X } from 'lucide-react'
import { api } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Badge, Card, Empty, PageLoader } from '../components/ui'
import { cx, formatDateTime, label } from '../lib/format'

export default function Audit() {
  const [rows, setRows] = useState<any[] | null>(null)
  const [query, setQuery] = useState('')
  const [entity, setEntity] = useState('')

  useEffect(() => {
    api.get<any[]>('/audit?limit=300').then(setRows).catch(() => undefined)
  }, [])

  const entities = useMemo(
    () => Array.from(new Set((rows ?? []).map((r) => r.entity_type))).sort(),
    [rows],
  )

  const filtered = useMemo(() => {
    if (!rows) return []
    const q = query.trim().toLowerCase()
    return rows.filter(
      (r) =>
        (!entity || r.entity_type === entity) &&
        (!q ||
          `${r.action} ${r.entity_type} ${r.user_name} ${JSON.stringify(r.changed_fields)}`
            .toLowerCase()
            .includes(q)),
    )
  }, [rows, query, entity])

  if (!rows) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Audit trail"
        description="Append-only. The database rejects UPDATE and DELETE on this table via trigger, so this is a record of what happened rather than a reconstruction of it. Every state transition carries the full gate evaluation as it stood at that moment."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            className="field pl-9"
            placeholder="Search the trail"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select className="field w-auto" value={entity} onChange={(e) => setEntity(e.target.value)}>
          <option value="">All entities</option>
          {entities.map((e) => (
            <option key={e} value={e}>
              {label(e)}
            </option>
          ))}
        </select>
        <span className="ml-auto text-sm text-ink-muted">
          {filtered.length} of {rows.length} entries
        </span>
      </div>

      <Card bodyClassName="p-0">
        {filtered.length === 0 ? (
          <Empty title="No audit entries match" />
        ) : (
          <ul className="divide-y">
            {filtered.map((r) => {
              const isTransition = r.action === 'STATE_TRANSITION'
              const cf = r.changed_fields ?? {}
              return (
                <li key={r.id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="mono rounded bg-surface-sunken px-1.5 py-0.5 text-ink">
                      {r.action}
                    </span>
                    <span className="text-sm text-ink-muted">{label(r.entity_type)}</span>
                    {isTransition && (
                      <>
                        <Badge value={cf.from} />
                        <span className="text-ink-faint">→</span>
                        <Badge value={cf.to} />
                        <span className="mono text-ink-faint">{cf.gate}</span>
                      </>
                    )}
                    <span className="ml-auto whitespace-nowrap text-xs text-ink-muted">
                      {r.user_name} · {formatDateTime(r.created_at)}
                    </span>
                  </div>

                  {isTransition && Array.isArray(cf.gate_evaluation) && (
                    <ul className="mt-2 flex flex-wrap gap-1.5">
                      {cf.gate_evaluation.map((c: any) => (
                        <li
                          key={c.id}
                          title={c.name}
                          className={cx(
                            'chip',
                            c.passed
                              ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                              : 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300',
                          )}
                        >
                          {c.passed ? (
                            <Check className="h-3 w-3" strokeWidth={3} />
                          ) : (
                            <X className="h-3 w-3" strokeWidth={3} />
                          )}
                          {c.id}
                        </li>
                      ))}
                    </ul>
                  )}

                  {isTransition && Array.isArray(cf.cascades) && cf.cascades.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {cf.cascades.map((e: any, i: number) => (
                        <li
                          key={i}
                          className="rounded-md border-l-2 border-accent bg-surface-sunken px-3 py-1.5 text-xs text-ink-muted"
                        >
                          <span className="mono text-ink-faint">{e.cascade}</span> →{' '}
                          {e.description}
                          {e.invariant && (
                            <span className="mono ml-1.5 rounded bg-surface px-1 py-0.5 text-ink-faint">
                              {e.invariant}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}

                  {!isTransition && Object.keys(cf).length > 0 && (
                    <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
                      {Object.entries(cf)
                        .slice(0, 8)
                        .map(([k, v]: any) => (
                          <div key={k} className="flex gap-1.5">
                            <dt className="shrink-0 font-medium text-ink-muted">{label(k)}:</dt>
                            <dd className="min-w-0 truncate text-ink-faint">
                              {v && typeof v === 'object' && 'from' in v
                                ? `${JSON.stringify(v.from)} → ${JSON.stringify(v.to)}`
                                : JSON.stringify(v)}
                            </dd>
                          </div>
                        ))}
                    </dl>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </>
  )
}
