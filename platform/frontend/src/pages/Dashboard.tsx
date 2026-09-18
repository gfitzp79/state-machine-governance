import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Boxes, FileText, Lock, PlayCircle, ShieldAlert, Target, Wrench } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Card, PageLoader, Stat, useToast } from '../components/ui'
import { Heatmap } from '../components/governance'
import { cx, ratingFill } from '../lib/format'

interface DashboardData {
  risk: Record<string, any>
  control: Record<string, any>
  policy: Record<string, any>
  treatment: Record<string, any>
  threat: Record<string, any>
}

const RATING_ORDER = ['Critical', 'High', 'Moderate', 'Moderate-Low', 'Low']
const PHASES = [
  'Intake',
  'Preconditions',
  'Scoring',
  'Treatment',
  'Readout',
  'Evidence_Residual',
  'Monitoring',
]

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [busy, setBusy] = useState(false)
  const { push } = useToast()

  const load = () => api.get<DashboardData>('/dashboard').then(setData)

  useEffect(() => {
    load().catch(() => undefined)
  }, [])

  const runJobs = async () => {
    setBusy(true)
    try {
      const result = await api.post<Record<string, any>>('/engine/jobs/run')
      const summary = [
        result.ce_expired?.length ? `${result.ce_expired.length} CE expiries` : null,
        result.acceptances_escalated?.length
          ? `${result.acceptances_escalated.length} acceptance escalations`
          : null,
        result.exceptions?.expired?.length
          ? `${result.exceptions.expired.length} exceptions expired`
          : null,
        result.sla_breached?.length ? `${result.sla_breached.length} SLA breaches` : null,
      ].filter(Boolean)
      push({
        kind: 'ok',
        title: 'Scheduled governance jobs completed',
        body: summary.length ? summary.join(', ') : 'Nothing was due.',
      })
      await load()
    } catch (err) {
      push({
        kind: 'error',
        title: 'Jobs failed',
        body: err instanceof ApiError ? err.message : String(err),
      })
    } finally {
      setBusy(false)
    }
  }

  if (!data) return <PageLoader />

  const { risk, control, policy, treatment, threat } = data
  const totalRated = RATING_ORDER.reduce((sum, r) => sum + (risk.by_rating[r] ?? 0), 0)

  return (
    <>
      <PageHeader
        title="Governance posture"
        description="Live state across the five lifecycles. Every number here is derived from the state machines, not entered by hand."
        actions={
          <button className="btn-ghost" onClick={runJobs} disabled={busy}>
            <PlayCircle className="h-4 w-4" />
            Run scheduled jobs
          </button>
        }
      />

      {/* attention strip */}
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <AttentionCard
          to="/risks?filter=above_appetite"
          icon={ShieldAlert}
          label="Risks above appetite"
          value={risk.above_appetite}
          hint={`${risk.open} open risks`}
          tone={risk.above_appetite > 0 ? 'bad' : 'good'}
        />
        <AttentionCard
          to="/risks"
          icon={Lock}
          label="Residual scores locked"
          value={risk.residual_locked}
          hint="awaiting the validation gate"
          tone={risk.residual_locked > 0 ? 'warn' : 'good'}
        />
        <AttentionCard
          to="/controls"
          icon={AlertTriangle}
          label="Controls in failure"
          value={control.in_failure}
          hint={`${control.ce_expired} with expired evidence`}
          tone={control.in_failure > 0 ? 'bad' : 'good'}
        />
        <AttentionCard
          to="/policies"
          icon={FileText}
          label="Exceptions expiring"
          value={policy.exceptions_expiring}
          hint={`${policy.exceptions_overdue} already overdue`}
          tone={policy.exceptions_overdue > 0 ? 'bad' : policy.exceptions_expiring > 0 ? 'warn' : 'good'}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Risk register by reported rating"
          subtitle="Reported rating is the residual where validated, otherwise the inherent score (RES-2)."
          className="lg:col-span-2"
        >
          <div className="space-y-2.5">
            {RATING_ORDER.map((rating) => {
              const count = risk.by_rating[rating] ?? 0
              const pct = totalRated ? (count / totalRated) * 100 : 0
              return (
                <div key={rating} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-xs font-medium text-ink-muted">
                    {rating}
                  </span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                    <div
                      className={cx('h-full rounded-full transition-all', ratingFill[rating])}
                      style={{ width: `${Math.max(pct, count ? 3 : 0)}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right text-sm font-semibold tabular-nums text-ink">
                    {count}
                  </span>
                </div>
              )
            })}
          </div>

          <div className="mt-6 border-t pt-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-muted">
              Distribution across the 7-phase lifecycle
            </p>
            <div className="flex flex-wrap gap-1.5">
              {PHASES.map((phase, i) => (
                <Link
                  key={phase}
                  to={`/risks?state=${phase}`}
                  className="flex items-center gap-1.5 rounded-md border bg-surface-sunken px-2.5 py-1.5 text-xs hover:border-accent"
                >
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-surface text-[10px] tabular-nums text-ink-muted">
                    {i + 1}
                  </span>
                  <span className="text-ink-muted">{phase.replace(/_/g, ' ')}</span>
                  <span className="font-semibold tabular-nums text-ink">
                    {risk.by_phase[phase] ?? 0}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </Card>

        <Card
          title="Risk heatmap"
          subtitle="Validated residual position where available, otherwise inherent."
        >
          <Heatmap counts={risk.heatmap} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <DomainCard
          to="/controls"
          icon={Boxes}
          title="Controls"
          rows={[
            ['Operating', control.operating, control.objectives],
            ['In failure', control.in_failure, null, control.in_failure > 0],
            ['Deployments degraded', control.deployments_degraded, null, control.deployments_degraded > 0],
            ['CE evidence expired', control.ce_expired, null, control.ce_expired > 0],
            ['Tests overdue', control.tests_overdue, null, control.tests_overdue > 0],
          ]}
        />
        <DomainCard
          to="/policies"
          icon={FileText}
          title="Policies"
          rows={[
            ['Active', policy.active, policy.total],
            ['Under revision', policy.under_revision],
            ['Review overdue', policy.review_overdue, null, policy.review_overdue > 0],
            ['Controls awaiting re-alignment', policy.realignment_pending, null, policy.realignment_pending > 0],
            ['Active exceptions', policy.exceptions_active],
          ]}
        />
        <DomainCard
          to="/treatments"
          icon={Wrench}
          title="Treatments"
          rows={[
            ['In progress', treatment.in_progress, treatment.total],
            ['Complete', treatment.complete],
            ['Awaiting GRC validation', treatment.awaiting_validation, null, treatment.awaiting_validation > 0],
            ['Awaiting owner commitment', treatment.awaiting_commitment, null, treatment.awaiting_commitment > 0],
            ['Overdue', treatment.overdue, null, treatment.overdue > 0],
          ]}
        />
        <DomainCard
          to="/threat-models"
          icon={Target}
          title="Threat models"
          rows={[
            ['Active', threat.active, threat.models],
            ['In review', threat.in_review],
            ['Scenarios unresolved', threat.unresolved, null, threat.unresolved > 0],
            ['Promoted to risk', threat.promoted],
            ['Re-opened by control failure', threat.reopened, null, threat.reopened > 0],
          ]}
        />
      </div>
    </>
  )
}

function AttentionCard({
  to,
  icon: Icon,
  label,
  value,
  hint,
  tone,
}: {
  to: string
  icon: any
  label: string
  value: number
  hint: string
  tone: 'good' | 'warn' | 'bad'
}) {
  return (
    <Link
      to={to}
      className={cx(
        'card flex items-center gap-4 px-5 py-4 transition-colors hover:border-accent',
        tone === 'bad' && 'border-rose-300 dark:border-rose-900',
      )}
    >
      <div
        className={cx(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
          tone === 'bad'
            ? 'bg-rose-100 text-rose-600 dark:bg-rose-950 dark:text-rose-400'
            : tone === 'warn'
              ? 'bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-400'
              : 'bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400',
        )}
      >
        <Icon className="h-5 w-5" />
      </div>
      <Stat label={label} value={value} hint={hint} tone={tone} />
    </Link>
  )
}

function DomainCard({
  to,
  icon: Icon,
  title,
  rows,
}: {
  to: string
  icon: any
  title: string
  rows: Array<[string, number] | [string, number, number | null] | [string, number, number | null, boolean]>
}) {
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-ink-muted" />
          {title}
        </span>
      }
      action={
        <Link to={to} className="text-xs font-medium text-accent hover:underline">
          Open
        </Link>
      }
      bodyClassName="px-5 py-3"
    >
      <dl className="divide-y">
        {rows.map(([label, value, total, alert]: any) => (
          <div key={label} className="flex items-center justify-between gap-3 py-2">
            <dt className="text-sm text-ink-muted">{label}</dt>
            <dd
              className={cx(
                'text-sm font-semibold tabular-nums',
                alert ? 'text-rose-600 dark:text-rose-400' : 'text-ink',
              )}
            >
              {value}
              {total != null && <span className="text-ink-faint"> / {total}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}
