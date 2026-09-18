import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  AlertTriangle,
  ChevronRight,
  Database,
  Info,
  Lock,
  ShieldCheck,
  ShieldOff,
  TriangleAlert,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge, Card, Empty } from './ui'
import { cx, formatDate, label } from '../lib/format'

/* ------------------------------------------------------ environmental context */

/**
 * The control and risk posture of the asset a threat model is scoped to.
 *
 * The banner at the top is not decoration. Showing existing controls during
 * threat modelling is useful for finding gaps and dangerous for finding threats:
 * a modeller who sees "MFA is deployed here" stops writing the spoofing scenario,
 * and when MFA fails there is no record the threat ever existed. The panel says
 * so explicitly, and the platform enforces it (TINV-7).
 */
export function EnvironmentPanel({ context }: { context: any }) {
  const [tab, setTab] = useState<'gaps' | 'controls' | 'risks'>('gaps')

  if (!context?.enabled) {
    return (
      <Card title="Environmental context">
        <Empty
          title="Context is disabled"
          hint="Set threat.context.show_environmental_context in governance.yml to surface the asset's control and risk posture here."
        />
      </Card>
    )
  }

  const cp = context.control_posture
  const rp = context.risk_posture
  const gaps: any[] = context.gaps ?? []
  const blocking = gaps.filter((g) => g.severity === 'blocking')

  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-xl border border-sky-300 bg-sky-50 px-4 py-3 dark:border-sky-900 dark:bg-sky-950/40">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-600 dark:text-sky-400" />
        <div>
          <p className="text-sm font-medium text-sky-900 dark:text-sky-200">
            Informative, not determinative
          </p>
          <p className="mt-0.5 text-sm leading-relaxed text-sky-800 dark:text-sky-300">
            {context.notice}
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <PostureStat
          label="Effective controls"
          value={cp.effective}
          total={cp.total_deployments}
          tone={cp.effective > 0 ? 'good' : 'bad'}
          hint="operating, with current evidence"
        />
        <PostureStat
          label="Weak or unproven"
          value={cp.weak}
          tone={cp.weak > 0 ? 'warn' : 'good'}
          hint="deployed but not assurable"
        />
        <PostureStat
          label="Risks above appetite"
          value={rp.above_appetite}
          total={rp.risks.length}
          tone={rp.above_appetite > 0 ? 'bad' : 'good'}
          hint="depending on these controls"
        />
        <PostureStat
          label="Control gaps"
          value={gaps.length}
          tone={blocking.length > 0 ? 'bad' : gaps.length > 0 ? 'warn' : 'good'}
          hint={blocking.length > 0 ? `${blocking.length} blocking sign-off` : 'observations'}
        />
      </div>

      <Card bodyClassName="p-0">
        <div className="flex gap-1 border-b px-2">
          {(
            [
              ['gaps', `Gaps (${gaps.length})`],
              ['controls', `Control posture (${cp.total_deployments})`],
              ['risks', `Risk posture (${rp.risks.length})`],
            ] as const
          ).map(([id, text]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cx(
                'relative px-3 py-2.5 text-sm font-medium transition-colors',
                tab === id ? 'text-accent' : 'text-ink-muted hover:text-ink',
              )}
            >
              {text}
              {tab === id && (
                <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" />
              )}
            </button>
          ))}
        </div>

        <div className="px-5 py-4">
          {tab === 'gaps' &&
            (gaps.length === 0 ? (
              <Empty
                title="No gaps detected"
                hint="Every sensitive component sits in a declared zone with operating control coverage."
              />
            ) : (
              <ul className="space-y-2">
                {gaps.map((g, i) => (
                  <li
                    key={i}
                    className={cx(
                      'flex gap-3 rounded-lg border px-3.5 py-3',
                      g.severity === 'blocking'
                        ? 'border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/30'
                        : g.severity === 'high'
                          ? 'border-orange-300 bg-orange-50 dark:border-orange-900 dark:bg-orange-950/30'
                          : 'bg-surface-sunken',
                    )}
                  >
                    {g.severity === 'blocking' ? (
                      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
                    ) : (
                      <TriangleAlert
                        className={cx(
                          'mt-0.5 h-4 w-4 shrink-0',
                          g.severity === 'high'
                            ? 'text-orange-600 dark:text-orange-400'
                            : 'text-ink-faint',
                        )}
                      />
                    )}
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-ink">{g.component}</span>
                        <span className="mono rounded bg-surface px-1.5 py-0.5 text-ink-faint">
                          {g.kind}
                        </span>
                        {g.severity === 'blocking' && (
                          <span className="chip border-rose-300 bg-rose-100 text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
                            blocks sign-off
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm leading-relaxed text-ink-muted">{g.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ))}

          {tab === 'controls' &&
            (cp.deployments.length === 0 ? (
              <Empty
                title="No controls deployed on this asset"
                hint="Every threat identified here is currently undefended by anything the control library knows about."
              />
            ) : (
              <ul className="space-y-1.5">
                {cp.deployments.map((d: any) => (
                  <li
                    key={d.deployment_id}
                    className={cx(
                      'rounded-lg border px-3 py-2.5',
                      d.status === 'effective'
                        ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20'
                        : 'bg-surface-sunken',
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      {d.status === 'effective' ? (
                        <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                      ) : (
                        <ShieldOff className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                      )}
                      <Link
                        to={`/controls/${d.objective_id}`}
                        className="mono text-ink-faint hover:text-accent"
                      >
                        {d.objective_reference}
                      </Link>
                      <span className="truncate text-sm text-ink">{d.objective_title}</span>
                      <Badge value={d.ce_rating} className="ml-auto" />
                      <Badge value={d.deployment_status} />
                    </div>
                    {d.reason && (
                      <p className="mt-1 pl-5 text-xs leading-relaxed text-ink-muted">
                        {d.reason}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            ))}

          {tab === 'risks' &&
            (rp.risks.length === 0 ? (
              <Empty
                title="No risks depend on controls here"
                hint="Nothing in the register is currently scored against this asset's controls."
              />
            ) : (
              <>
                <p className="mb-3 text-xs text-ink-muted">
                  Exposure the register already carries on this asset. A threat that maps
                  onto one of these should reference it rather than create a duplicate
                  (TINV-8).
                </p>
                <ul className="space-y-1.5">
                  {rp.risks.map((r: any) => (
                    <li
                      key={r.id}
                      className="flex flex-wrap items-center gap-2 rounded-lg border bg-surface-sunken px-3 py-2.5"
                    >
                      <Link
                        to={`/risks/${r.id}`}
                        className="mono text-ink-faint hover:text-accent"
                      >
                        {r.reference}
                      </Link>
                      <span className="min-w-0 flex-1 truncate text-sm text-ink">
                        {r.title}
                      </span>
                      {r.residual_score_locked && (
                        <span
                          className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300"
                          title="Residual is locked; this risk currently reports its inherent score"
                        >
                          <Lock className="h-3 w-3" />
                          residual locked
                        </span>
                      )}
                      {r.treatment_strategy === 'Accept' && (
                        <span className="chip border-line bg-surface text-ink-muted">
                          accepted to {formatDate(r.acceptance_expiry_date)}
                        </span>
                      )}
                      <Badge value={r.reported_rating} />
                    </li>
                  ))}
                </ul>
              </>
            ))}
        </div>
      </Card>
    </div>
  )
}

function PostureStat({
  label: text,
  value,
  total,
  hint,
  tone,
}: {
  label: string
  value: number
  total?: number
  hint: string
  tone: 'good' | 'warn' | 'bad'
}) {
  return (
    <div
      className={cx(
        'card px-4 py-3',
        tone === 'bad' && 'border-rose-300 dark:border-rose-900',
        tone === 'warn' && 'border-amber-300 dark:border-amber-900',
      )}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        {text}
      </p>
      <p
        className={cx(
          'mt-1 text-2xl font-semibold tabular-nums',
          tone === 'bad'
            ? 'text-rose-600 dark:text-rose-400'
            : tone === 'warn'
              ? 'text-amber-600 dark:text-amber-400'
              : 'text-emerald-600 dark:text-emerald-400',
        )}
      >
        {value}
        {total != null && <span className="text-base text-ink-faint"> / {total}</span>}
      </p>
      <p className="mt-0.5 text-xs text-ink-faint">{hint}</p>
    </div>
  )
}

/* --------------------------------------------------------------- components */

const ZONE_TONE: Record<number, string> = {
  0: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300',
  1: 'border-orange-300 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/50 dark:text-orange-300',
  2: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300',
  3: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300',
}

export function ClassificationBadge({
  classification,
  sensitive,
}: {
  classification: string | null
  sensitive?: boolean
}) {
  if (!classification) {
    return <span className="chip border-dashed border-line text-ink-faint">unclassified</span>
  }
  return (
    <span
      className={cx(
        'chip',
        sensitive
          ? 'border-purple-300 bg-purple-50 text-purple-700 dark:border-purple-900 dark:bg-purple-950/50 dark:text-purple-300'
          : 'border-line bg-surface-sunken text-ink-muted',
      )}
    >
      <Database className="h-3 w-3" />
      {classification}
    </span>
  )
}

export function TrustZoneBadge({
  zone,
  level,
}: {
  zone: string | null
  level: number | null
}) {
  if (!zone) {
    return <span className="chip border-dashed border-line text-ink-faint">no zone</span>
  }
  return (
    <span className={cx('chip', ZONE_TONE[level ?? 2] ?? 'border-line bg-surface-sunken')}>
      {label(zone)}
    </span>
  )
}

/** One decomposed component with everything that determines what its compromise costs. */
export function ComponentRow({
  component,
  coverage,
  onEdit,
  onAddScenario,
}: {
  component: any
  coverage?: any
  onEdit: () => void
  onAddScenario: () => void
}) {
  const [open, setOpen] = useState(false)
  const uncovered = coverage && coverage.effective_count === 0
  const unanalysed = component.is_sensitive && component.scenario_count === 0

  return (
    <li
      className={cx(
        'rounded-lg border',
        unanalysed
          ? 'border-rose-300 bg-rose-50/50 dark:border-rose-900 dark:bg-rose-950/20'
          : 'bg-surface-sunken',
      )}
    >
      <button
        className="flex w-full items-start gap-3 px-3.5 py-3 text-left"
        onClick={() => setOpen(!open)}
      >
        <ChevronRight
          className={cx(
            'mt-0.5 h-4 w-4 shrink-0 text-ink-faint transition-transform',
            open && 'rotate-90',
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{component.name}</span>
            <Badge value={component.component_type} />
            <ClassificationBadge
              classification={component.data_classification}
              sensitive={component.is_sensitive}
            />
            <TrustZoneBadge zone={component.trust_zone} level={component.trust_level} />
            {component.exposure && (
              <span className="chip border-line bg-surface text-ink-muted">
                {label(component.exposure)}
              </span>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>
              {component.scenario_count} scenario{component.scenario_count === 1 ? '' : 's'}
            </span>
            {component.asset_name && <span>· on {component.asset_name}</span>}
            {coverage && (
              <span
                className={cx(
                  uncovered ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400',
                )}
              >
                · {coverage.effective_count} effective control
                {coverage.effective_count === 1 ? '' : 's'} on its asset
              </span>
            )}
            {unanalysed && (
              <span className="chip border-rose-300 bg-rose-100 text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
                <AlertTriangle className="h-3 w-3" />
                sensitive, no scenario (TINV-11)
              </span>
            )}
          </div>
        </div>
      </button>

      {open && (
        <div className="space-y-3 border-t px-3.5 py-3">
          {component.description && (
            <p className="text-sm text-ink-muted">{component.description}</p>
          )}

          {component.data_types?.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                Data handled
              </p>
              <div className="flex flex-wrap gap-1">
                {component.data_types.map((d: string) => (
                  <span key={d} className="chip border-line bg-surface text-ink-muted">
                    {label(d)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {coverage && (
            <div>
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                Controls operating on this component's asset
              </p>
              {coverage.effective.length === 0 ? (
                <p className="text-sm text-ink-muted">
                  Nothing operating with current evidence. Anything identified here is
                  currently undefended.
                </p>
              ) : (
                <ul className="space-y-1">
                  {coverage.effective.map((d: any) => (
                    <li
                      key={d.deployment_id}
                      className="flex flex-wrap items-center gap-2 rounded border border-emerald-200 bg-emerald-50/60 px-2.5 py-1.5 text-xs dark:border-emerald-900 dark:bg-emerald-950/20"
                    >
                      <ShieldCheck className="h-3 w-3 shrink-0 text-emerald-600" />
                      <span className="mono">{d.objective_reference}</span>
                      <span className="text-ink-muted">{label(d.family)}</span>
                      <Badge value={d.ce_rating} className="ml-auto" />
                    </li>
                  ))}
                </ul>
              )}
              {coverage.stride_categories_without_control.length > 0 && (
                <p className="mt-2 text-xs text-ink-muted">
                  No control family present for:{' '}
                  <span className="text-ink">
                    {coverage.stride_categories_without_control.map(label).join(', ')}
                  </span>
                  . A hint for where to look, not a claim that a threat exists.
                </p>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <button className="btn-ghost btn-sm" onClick={onEdit}>
              Edit attributes
            </button>
            <button className="btn-ghost btn-sm" onClick={onAddScenario}>
              Identify a threat here
            </button>
          </div>
        </div>
      )}
    </li>
  )
}
