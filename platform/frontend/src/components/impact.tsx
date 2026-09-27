import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight, CircleSlash, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Badge } from './ui'
import { cx, label } from '../lib/format'

/**
 * What a control test changed, and where it stopped (codified-rules §25.4).
 *
 * The record is computed by the server in the transaction that recorded the
 * test and stored on the append-only test row, so this renders lineage as it
 * was at the time rather than re-deriving it from a register that has since
 * moved on. It answers the owner's question after a test: what did that do to
 * MY framework and MY risk?
 */

export interface ImpactData {
  failure_type: string | null
  design_failure: boolean
  tested_assets: string[]
  frameworks: FrameworkImpact[]
  risks: RiskImpact[]
  totals: {
    frameworks_affected: number
    requirements_lost: number
    risks_affected: number
    risks_proposed_above_appetite: number
  }
  population?: Population[]
  results?: { deployment: string; asset: string; result: string; failure_type: string | null }[]
}

interface FrameworkImpact {
  framework_id: string
  name: string
  rule: string
  asset_in_scope: boolean
  scoped_asset_names: string[]
  coverage_pct_before: number | null
  coverage_pct_after: number | null
  verdict: 'requirements_lost' | 'out_of_scope' | 'still_covered' | 'restorable' | 'no_change'
  summary: string
  requirements: {
    ref: string
    title: string
    before: string
    after: string
    lost: boolean
    restorable: boolean
    reason: string | null
    in_scope_assets: number
    reached_before: number
    reached_after: number
  }[]
}

interface RiskImpact {
  id: string
  reference: string
  title: string
  scope_declared: boolean
  scope_asset_names: string[]
  asset_in_scope: boolean
  affected: boolean
  ce_before: string
  ce_after: string
  ceiling_before: number
  ceiling_after: number
  residual_before: { score: number | null; rating: string | null }
  proposed: {
    score: number
    rating: string
    appetite: string
    above_appetite: boolean
    changed: boolean
  } | null
  summary: string
}

interface Population {
  framework_id: string
  in_scope: number
  tested: string[]
  failed: string[]
  untested: string[]
  not_deployed: string[]
  tested_pct: number | null
}

const RULE_TEXT: Record<string, string> = {
  all_in_scope: 'Every in-scope asset must carry the control',
  any_in_scope: 'Covered while any in-scope asset carries it',
}

const VERDICT: Record<FrameworkImpact['verdict'], { tone: string; icon: typeof ShieldAlert }> = {
  requirements_lost: {
    tone: 'border-rose-300 bg-rose-50/70 dark:border-rose-900 dark:bg-rose-950/30',
    icon: ShieldAlert,
  },
  still_covered: {
    tone: 'border-amber-300 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/25',
    icon: AlertTriangle,
  },
  restorable: {
    tone: 'border-sky-300 bg-sky-50/60 dark:border-sky-900 dark:bg-sky-950/25',
    icon: ShieldCheck,
  },
  out_of_scope: { tone: 'bg-surface-sunken', icon: CircleSlash },
  no_change: { tone: 'bg-surface-sunken', icon: ShieldCheck },
}

function Delta({ before, after, suffix = '' }: { before: any; after: any; suffix?: string }) {
  const fmt = (v: any) => (v === null || v === undefined ? 'none' : `${v}${suffix}`)
  const moved = before !== after
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      <span className={cx(moved && 'text-ink-faint line-through decoration-1')}>{fmt(before)}</span>
      {moved && (
        <>
          <ArrowRight className="h-3 w-3 text-ink-faint" />
          <span className="font-semibold text-ink">{fmt(after)}</span>
        </>
      )}
    </span>
  )
}

export function ImpactSummary({ impact }: { impact: ImpactData }) {
  const t = impact.totals
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {impact.failure_type && <Badge value="Fail">{impact.failure_type} failure</Badge>}
      <span
        className={cx(
          'chip',
          t.requirements_lost
            ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300'
            : 'border-line bg-surface-sunken text-ink-muted',
        )}
      >
        {t.requirements_lost} requirement{t.requirements_lost === 1 ? '' : 's'} lost
      </span>
      <span
        className={cx(
          'chip',
          t.risks_affected
            ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300'
            : 'border-line bg-surface-sunken text-ink-muted',
        )}
      >
        {t.risks_affected} risk{t.risks_affected === 1 ? '' : 's'} affected
      </span>
      {t.risks_proposed_above_appetite > 0 && (
        <span className="chip border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300">
          {t.risks_proposed_above_appetite} proposed above appetite
        </span>
      )}
    </div>
  )
}

export function ImpactReport({ impact }: { impact: ImpactData }) {
  return (
    <div className="space-y-5" data-testid="impact-report">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-surface-sunken px-4 py-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Tested
          </p>
          <p className="mt-0.5 text-sm font-medium text-ink">
            {impact.tested_assets.join(', ') || 'None'}
          </p>
        </div>
        <div className="ml-auto">
          <ImpactSummary impact={impact} />
        </div>
      </div>

      {impact.design_failure && (
        <p className="flex items-start gap-2 rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <span className="font-semibold">Design failure.</span> The control does not work as
            designed, so it entered Failure everywhere it runs (DL-1). Scope did not limit this:
            every framework and every risk it carries is affected.
          </span>
        </p>
      )}

      {impact.population && impact.population.length > 0 && (
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Population tested
          </h4>
          <div className="grid gap-2 sm:grid-cols-2">
            {impact.population.map((p) => (
              <div key={p.framework_id} className="rounded-lg border px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="mono text-sm font-semibold text-ink">{p.framework_id}</span>
                  <span className="text-xs tabular-nums text-ink-muted">
                    {p.tested.length} of {p.in_scope} in-scope assets tested
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-sunken">
                  <div
                    className="h-full bg-accent"
                    style={{ width: `${p.tested_pct ?? 0}%` }}
                  />
                </div>
                <dl className="mt-2 space-y-0.5 text-xs">
                  {p.failed.length > 0 && (
                    <div className="text-rose-700 dark:text-rose-300">
                      <dt className="inline font-semibold">Failed: </dt>
                      <dd className="inline">{p.failed.join(', ')}</dd>
                    </div>
                  )}
                  {p.untested.length > 0 && (
                    <div className="text-amber-700 dark:text-amber-300">
                      <dt className="inline font-semibold">Not tested: </dt>
                      <dd className="inline">{p.untested.join(', ')}</dd>
                    </div>
                  )}
                  {p.not_deployed.length > 0 && (
                    <div className="text-ink-muted">
                      <dt className="inline font-semibold">In scope, control not deployed: </dt>
                      <dd className="inline">{p.not_deployed.join(', ')}</dd>
                    </div>
                  )}
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Frameworks ({impact.frameworks.length})
        </h4>
        {impact.frameworks.length === 0 ? (
          <p className="text-sm text-ink-faint">This control carries no requirement of an adopted framework.</p>
        ) : (
          <ul className="space-y-2">
            {impact.frameworks.map((f) => {
              const v = VERDICT[f.verdict]
              const Icon = v.icon
              return (
                <li
                  key={f.framework_id}
                  className={cx('rounded-lg border px-4 py-3', v.tone)}
                  data-testid={`impact-framework-${f.framework_id}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Icon className="h-4 w-4 shrink-0 text-ink-muted" />
                    <span className="font-medium text-ink">{f.name}</span>
                    <span className="chip border-line bg-surface text-ink-muted" title={RULE_TEXT[f.rule]}>
                      {label(f.rule)}
                    </span>
                    <span
                      className={cx(
                        'chip',
                        f.asset_in_scope
                          ? 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-300'
                          : 'border-line bg-surface text-ink-faint',
                      )}
                    >
                      {f.asset_in_scope ? 'tested asset in scope' : 'tested asset out of scope'}
                    </span>
                    <span className="ml-auto text-sm text-ink-muted">
                      coverage{' '}
                      <Delta before={f.coverage_pct_before} after={f.coverage_pct_after} suffix="%" />
                    </span>
                  </div>
                  <p className="mt-1 pl-6 text-sm text-ink">{f.summary}</p>
                  {f.requirements.some((r) => r.before !== r.after || r.lost || r.reached_before !== r.reached_after) && (
                    <ul className="mt-2 space-y-1 pl-6">
                      {f.requirements.map((r) => (
                        <li key={r.ref} className="text-xs">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="mono text-ink-faint">{r.ref}</span>
                            <span className="text-ink-muted">{r.title}</span>
                            <span className="ml-auto inline-flex items-center gap-1">
                              <Badge value={r.before === 'Covered' ? 'Pass' : r.before === 'Gap' ? 'Fail' : null}>
                                {label(r.before)}
                              </Badge>
                              {r.before !== r.after && (
                                <>
                                  <ArrowRight className="h-3 w-3 text-ink-faint" />
                                  <Badge value={r.after === 'Covered' ? 'Pass' : r.after === 'Gap' ? 'Fail' : null}>
                                    {label(r.after)}
                                  </Badge>
                                </>
                              )}
                            </span>
                          </div>
                          <p className="mt-0.5 text-ink-muted">
                            In-scope assets carrying the control:{' '}
                            <Delta before={r.reached_before} after={r.reached_after} /> of {r.in_scope_assets}
                          </p>
                          {r.reason && <p className="mt-0.5 text-rose-700 dark:text-rose-300">{r.reason}</p>}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Risks ({impact.risks.length})
        </h4>
        {impact.risks.length === 0 ? (
          <p className="text-sm text-ink-faint">No open risk is linked to this control.</p>
        ) : (
          <ul className="space-y-2">
            {impact.risks.map((r) => (
              <li
                key={r.id}
                className={cx(
                  'rounded-lg border px-4 py-3',
                  r.affected
                    ? 'border-amber-300 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/25'
                    : 'bg-surface-sunken',
                )}
                data-testid={`impact-risk-${r.reference}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/risks/${r.id}`} className="mono text-sm font-semibold text-accent hover:underline">
                    {r.reference}
                  </Link>
                  <span className="min-w-0 truncate text-sm text-ink">{r.title}</span>
                  <span
                    className={cx(
                      'chip ml-auto',
                      r.affected
                        ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300'
                        : 'border-line bg-surface text-ink-faint',
                    )}
                  >
                    {r.affected ? 'affected' : 'not affected'}
                  </span>
                </div>
                <p className="mt-1 text-xs text-ink-muted">
                  {r.scope_declared
                    ? `Scope: ${r.scope_asset_names.join(', ')}${r.asset_in_scope ? ' (includes the tested asset)' : ''}`
                    : 'No scope declared: every deployment counts toward this risk'}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-muted">
                  <span className="inline-flex items-center gap-1">
                    CE <Badge value={r.ce_before} />
                    {r.ce_before !== r.ce_after && (
                      <>
                        <ArrowRight className="h-3 w-3" />
                        <Badge value={r.ce_after} />
                      </>
                    )}
                  </span>
                  <span>
                    likelihood reduction up to <Delta before={r.ceiling_before} after={r.ceiling_after} />
                  </span>
                  {r.residual_before.score !== null && (
                    <span className="inline-flex items-center gap-1">
                      residual {r.residual_before.score}
                      {r.residual_before.rating && <Badge value={r.residual_before.rating} />}
                    </span>
                  )}
                  {r.proposed && r.proposed.changed && (
                    <span className="inline-flex items-center gap-1 font-medium text-ink">
                      proposed {r.proposed.score} <Badge value={r.proposed.rating} />
                      {r.proposed.above_appetite && (
                        <span className="chip border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300">
                          above appetite
                        </span>
                      )}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-sm text-ink">{r.summary}</p>
              </li>
            ))}
          </ul>
        )}
        {impact.risks.some((r) => r.proposed?.changed) && (
          <p className="mt-2 text-xs text-ink-muted">
            A proposed residual is never applied. The residual stays locked until the full
            validation gate passes (RINV-1).
          </p>
        )}
      </section>
    </div>
  )
}
