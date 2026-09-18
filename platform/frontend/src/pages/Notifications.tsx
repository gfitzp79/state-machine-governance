import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Check } from 'lucide-react'
import { api } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Card, Empty, PageLoader } from '../components/ui'
import { cx, formatDateTime, label } from '../lib/format'

const ROUTE: Record<string, string> = {
  risk: '/risks',
  control_objective: '/controls',
  control_deployment: '/controls',
  policy: '/policies',
  policy_exception: '/policies',
  treatment: '/treatments',
  threat_model: '/threat-models',
}

export default function Notifications() {
  const [rows, setRows] = useState<any[] | null>(null)

  const load = () => api.get<any[]>('/notifications').then(setRows)

  useEffect(() => {
    load().catch(() => undefined)
  }, [])

  if (!rows) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Written by cascade handlers and scheduled jobs. Every entry here corresponds to a rule firing, not to a generic activity feed."
      />

      <Card bodyClassName="p-0">
        {rows.length === 0 ? (
          <Empty
            title="Nothing waiting"
            hint="Cascade effects and SLA breaches assigned to you will appear here."
          />
        ) : (
          <ul className="divide-y">
            {rows.map((n) => {
              const base = ROUTE[n.entity_type ?? '']
              return (
                <li
                  key={n.id}
                  className={cx('flex gap-3 px-5 py-3.5', !n.is_read && 'bg-accent-soft/30')}
                >
                  <Bell
                    className={cx(
                      'mt-0.5 h-4 w-4 shrink-0',
                      n.is_read ? 'text-ink-faint' : 'text-accent',
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-ink">{n.title}</p>
                      <span className="mono rounded bg-surface-sunken px-1.5 py-0.5 text-ink-faint">
                        {n.event_type}
                      </span>
                    </div>
                    {n.body && <p className="mt-0.5 text-sm text-ink-muted">{n.body}</p>}
                    <p className="mt-1 text-xs text-ink-faint">
                      {label(n.entity_type)} · {formatDateTime(n.created_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-start gap-2">
                    {base && n.entity_id && (
                      <Link to={`${base}/${n.entity_id}`} className="btn-ghost btn-sm">
                        Open
                      </Link>
                    )}
                    {!n.is_read && (
                      <button
                        className="btn-ghost btn-sm"
                        onClick={async () => {
                          await api.post(`/notifications/${n.id}/read`)
                          await load()
                        }}
                        aria-label="Mark read"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </>
  )
}
