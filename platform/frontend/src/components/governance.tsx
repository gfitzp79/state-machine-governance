import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  ArrowRight,
  Check,
  ChevronRight,
  Lock,
  LockOpen,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react'
import { Badge, Card, Empty, Spinner, Table } from './ui'
import { cx, label, ratingFill, tone } from '../lib/format'

export interface CheckResult {
  id: string
  name: string
  passed: boolean
  detail: string
}

export interface GateOption {
  gate: string
  source: string
  target: string
  passed: boolean
  checks: CheckResult[]
  roles: string[]
  role_permitted: boolean
  description: string
}

/**
 * The gate panel. This is the component the whole platform exists to make
 * possible: for every transition available from the current state, it shows each
 * named precondition and whether it currently holds. A blocked transition is
 * never a mystery.
 */
export function GatePanel({
  gates,
  onFire,
  busy,
  reasonPrompt,
}: {
  gates: GateOption[]
  onFire: (target: string, reason?: string) => void
  busy?: string | null
  reasonPrompt?: (target: string) => boolean
}) {
  const [open, setOpen] = useState<string | null>(gates.find((g) => !g.passed)?.target ?? null)
  const [reason, setReason] = useState('')

  if (!gates.length) {
    return <Empty title="No transitions available" hint="This record is in a terminal state." />
  }

  return (
    <div className="space-y-2.5">
      {gates.map((gate) => {
        const expanded = open === gate.target
        const blockedByRole = !gate.role_permitted
        const failures = gate.checks.filter((c) => !c.passed)
        const canFire = gate.passed && gate.role_permitted
        const needsReason = reasonPrompt?.(gate.target) ?? false

        return (
          <div
            key={gate.target}
            className={cx(
              'rounded-lg border transition-colors',
              canFire
                ? 'border-emerald-300 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/20'
                : 'bg-surface-sunken',
            )}
          >
            <button
              className="flex w-full items-center gap-3 px-3.5 py-3 text-left"
              onClick={() => setOpen(expanded ? null : gate.target)}
            >
              <ChevronRight
                className={cx(
                  'h-4 w-4 shrink-0 text-ink-faint transition-transform',
                  expanded && 'rotate-90',
                )}
              />
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Badge value={gate.source} />
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                <Badge value={gate.target} />
              </div>
              <span className="mono hidden shrink-0 text-ink-faint sm:inline">{gate.gate}</span>
              {canFire ? (
                <span className="chip border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
                  <ShieldCheck className="h-3 w-3" /> Open
                </span>
              ) : (
                <span className="chip border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300">
                  <ShieldAlert className="h-3 w-3" />
                  {blockedByRole ? 'Role' : `${failures.length} blocking`}
                </span>
              )}
            </button>

            {expanded && (
              <div className="space-y-3 border-t px-3.5 py-3">
                {gate.description && (
                  <p className="text-xs leading-relaxed text-ink-muted">{gate.description}</p>
                )}

                {blockedByRole && (
                  <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300">
                    This transition requires one of:{' '}
                    <span className="font-medium">{gate.roles.map(label).join(', ')}</span>
                  </p>
                )}

                {gate.checks.length === 0 ? (
                  <p className="text-xs text-ink-faint">
                    This transition has no preconditions beyond role authorisation.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {gate.checks.map((check) => (
                      <li key={check.id} className="flex gap-2.5">
                        <span
                          className={cx(
                            'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
                            check.passed
                              ? 'bg-emerald-500 text-white'
                              : 'bg-rose-500 text-white',
                          )}
                        >
                          {check.passed ? (
                            <Check className="h-2.5 w-2.5" strokeWidth={3} />
                          ) : (
                            <X className="h-2.5 w-2.5" strokeWidth={3} />
                          )}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-ink">
                            {check.name}{' '}
                            <span className="mono ml-1 rounded bg-surface px-1.5 py-0.5 text-ink-faint">
                              {check.id}
                            </span>
                          </p>
                          {!check.passed && check.detail && (
                            <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
                              {check.detail}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {canFire && needsReason && (
                  <input
                    className="field"
                    placeholder="Reason (required for this transition)"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                )}

                <div className="flex justify-end">
                  <button
                    className="btn-primary btn-sm"
                    disabled={!canFire || busy === gate.target || (needsReason && !reason.trim())}
                    onClick={() => onFire(gate.target, reason.trim() || undefined)}
                  >
                    {busy === gate.target && <Spinner className="h-3 w-3" />}
                    Advance to {label(gate.target)}
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Horizontal phase rail for the 7-phase risk lifecycle. */
export function LifecycleRail({
  states,
  current,
  terminal,
}: {
  states: string[]
  current: string
  terminal?: string[]
}) {
  const index = states.indexOf(current)
  const isTerminal = terminal?.includes(current)
  return (
    <ol className="flex flex-wrap items-center gap-1">
      {states.map((state, i) => {
        const done = !isTerminal && i < index
        const active = state === current
        return (
          <li key={state} className="flex items-center gap-1">
            <span
              className={cx(
                'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium',
                active
                  ? 'border-accent bg-accent text-white'
                  : done
                    ? 'border-line bg-surface-sunken text-ink-muted'
                    : 'border-dashed border-line bg-transparent text-ink-faint',
              )}
            >
              <span
                className={cx(
                  'flex h-4 w-4 items-center justify-center rounded-full text-[10px] tabular-nums',
                  active ? 'bg-white/25' : done ? 'bg-emerald-500 text-white' : 'bg-surface-sunken',
                )}
              >
                {done ? <Check className="h-2.5 w-2.5" strokeWidth={3} /> : i + 1}
              </span>
              {label(state)}
            </span>
            {i < states.length - 1 && <span className="text-ink-faint">·</span>}
          </li>
        )
      })}
      {isTerminal && (
        <li className="ml-1">
          <Badge value={current} />
        </li>
      )}
    </ol>
  )
}

export interface InvariantResult {
  id: string
  entity: string
  rule: string
  layer: string
  mechanism: string
  violation: string
  spec_ref: string
  satisfied?: boolean
  detail?: string
}

export function InvariantList({ invariants }: { invariants: InvariantResult[] }) {
  if (!invariants.length) return <Empty title="No invariants registered for this entity" />
  const breached = invariants.filter((i) => i.satisfied === false)
  return (
    <div className="space-y-3">
      {breached.length > 0 && (
        <p className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300">
          {breached.length} invariant{breached.length === 1 ? '' : 's'} currently unsatisfied on
          this record. Writes that would deepen the violation are refused.
        </p>
      )}
      <ul className="divide-y">
        {invariants.map((inv) => (
          <li key={inv.id} className="flex gap-3 py-2.5">
            <span
              className={cx(
                'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
                inv.satisfied === false ? 'bg-rose-500 text-white' : 'bg-emerald-500 text-white',
              )}
            >
              {inv.satisfied === false ? (
                <X className="h-2.5 w-2.5" strokeWidth={3} />
              ) : (
                <Check className="h-2.5 w-2.5" strokeWidth={3} />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono rounded bg-surface-sunken px-1.5 py-0.5 text-ink">
                  {inv.id}
                </span>
                <span className="chip border-line bg-surface-sunken text-ink-faint">
                  {inv.layer}
                </span>
                <span className="text-[11px] text-ink-faint">{inv.spec_ref}</span>
              </div>
              <p className="mt-1 text-sm text-ink">{inv.rule}</p>
              <p className="mt-0.5 text-xs text-ink-muted">{inv.mechanism}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export interface CEResolutionData {
  effective_ce: string
  max_likelihood_reduction: number
  contributing: Record<string, unknown>[]
  excluded: Record<string, unknown>[]
}

/**
 * Shows which controls counted toward the score and which did not, naming the
 * rule that excluded each one. This is the answer to "why didn't my control
 * reduce the score?", which is the question GRC tooling usually cannot answer.
 */
export function CEResolution({ data }: { data: CEResolutionData }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface-sunken px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Effective control effectiveness
          </p>
          <div className="mt-1 flex items-center gap-2">
            <Badge value={data.effective_ce} />
            <span className="text-xs text-ink-muted">
              worst case across qualifying deployments (CINV-6)
            </span>
          </div>
        </div>
        <div className="ml-auto text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Permitted likelihood reduction
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-ink">
            {data.max_likelihood_reduction === 0
              ? 'none'
              : `up to ${data.max_likelihood_reduction} level${data.max_likelihood_reduction === 1 ? '' : 's'}`}
          </p>
        </div>
      </div>

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Contributing ({data.contributing.length})
        </h4>
        {data.contributing.length === 0 ? (
          <p className="text-sm text-ink-faint">
            No control deployment currently qualifies, so no likelihood reduction is permitted.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {data.contributing.map((c, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-sm dark:border-emerald-900 dark:bg-emerald-950/20"
              >
                <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" strokeWidth={3} />
                <span className="mono">{String(c.deployment_reference ?? c.reference ?? '')}</span>
                <span className="text-ink-muted">{String(c.title ?? '')}</span>
                {c.asset ? (
                  <span className="text-xs text-ink-faint">on {String(c.asset)}</span>
                ) : null}
                <Badge value={String(c.ce_rating ?? '')} className="ml-auto" />
              </li>
            ))}
          </ul>
        )}
      </div>

      {data.excluded.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Excluded ({data.excluded.length})
          </h4>
          <ul className="space-y-1.5">
            {data.excluded.map((c, i) => (
              <li key={i} className="rounded-md border bg-surface-sunken px-3 py-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <X className="h-3.5 w-3.5 shrink-0 text-ink-faint" strokeWidth={3} />
                  <span className="mono">
                    {String(c.deployment_reference ?? c.reference ?? '')}
                  </span>
                  <span className="text-ink-muted">{String(c.title ?? '')}</span>
                  <Badge value={String(c.ce_rating ?? '')} className="ml-auto" />
                </div>
                <p className="mt-1 pl-6 text-xs text-ink-muted">{String(c.reason ?? '')}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** 5x5 risk heatmap. Cell colour is the rating band; the number is the count. */
export function Heatmap({
  counts,
  onSelect,
}: {
  counts: Record<string, number>
  onSelect?: (impact: number, likelihood: number) => void
}) {
  const band = (score: number) =>
    score >= 20 ? 'Critical' : score >= 15 ? 'High' : score >= 10 ? 'Moderate' : score >= 5 ? 'Moderate-Low' : 'Low'

  return (
    <div className="overflow-x-auto">
      <div className="inline-block min-w-full">
        <div className="flex">
          <div className="w-24 shrink-0" />
          <div className="flex-1 pb-1 text-center text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Impact
          </div>
        </div>
        {[5, 4, 3, 2, 1].map((likelihood) => (
          <div key={likelihood} className="flex items-stretch">
            <div className="flex w-24 shrink-0 items-center justify-end pr-2 text-[11px] text-ink-muted">
              {likelihood === 3 && (
                <span className="mr-auto pl-1 font-semibold uppercase tracking-wider">
                  Likelihood
                </span>
              )}
              <span className="tabular-nums">{likelihood}</span>
            </div>
            <div className="grid flex-1 grid-cols-5 gap-1 pb-1">
              {[1, 2, 3, 4, 5].map((impact) => {
                const score = impact * likelihood
                const key = `${impact}x${likelihood}`
                const count = counts[key] ?? 0
                return (
                  <button
                    key={impact}
                    onClick={() => onSelect?.(impact, likelihood)}
                    title={`Impact ${impact} × Likelihood ${likelihood} = ${score} (${band(score)})`}
                    className={cx(
                      'relative flex h-12 items-center justify-center rounded-md text-sm font-semibold tabular-nums transition-transform',
                      ratingFill[band(score)],
                      count > 0 ? 'text-white' : 'text-white/35',
                      onSelect && 'hover:scale-[1.04]',
                      count === 0 && 'opacity-30',
                    )}
                  >
                    {count > 0 ? count : ''}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        <div className="flex">
          <div className="w-24 shrink-0" />
          <div className="grid flex-1 grid-cols-5 gap-1 pt-0.5">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="text-center text-[11px] tabular-nums text-ink-muted">
                {i}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Small lock indicator used wherever a field group is gated. */
export function LockState({ locked, children }: { locked: boolean; children?: ReactNode }) {
  return (
    <span
      className={cx(
        'chip',
        locked
          ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300'
          : 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300',
      )}
    >
      {locked ? <Lock className="h-3 w-3" /> : <LockOpen className="h-3 w-3" />}
      {children ?? (locked ? 'Locked' : 'Unlocked')}
    </span>
  )
}

/** Gate checklist used for the five residual conditions and the four preconditions. */
export function ConditionList({
  conditions,
  descriptions,
  onToggle,
  disabled,
}: {
  conditions: Record<string, boolean>
  descriptions?: Record<string, string>
  onToggle?: (key: string, value: boolean) => void
  disabled?: boolean
}) {
  return (
    <ul className="space-y-1.5">
      {Object.entries(conditions).map(([key, value]) => (
        <li
          key={key}
          className={cx(
            'flex items-start gap-3 rounded-md border px-3 py-2.5',
            value
              ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20'
              : 'bg-surface-sunken',
          )}
        >
          <input
            type="checkbox"
            checked={value}
            disabled={disabled || !onToggle}
            onChange={(e) => onToggle?.(key, e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-emerald-600"
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{label(key)}</p>
            {descriptions?.[key] && (
              <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{descriptions[key]}</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}

/** Renders a state machine definition as a transition table. */
export function MachineTable({ machine }: { machine: any }) {
  return (
    <Card
      title={label(machine.entity)}
      subtitle={`${machine.states.length} states · ${machine.transitions.length} transitions · driven by ${machine.state_field}`}
      bodyClassName="p-0"
    >
      <div className="flex flex-wrap gap-1.5 border-b px-5 py-3">
        {machine.states.map((s: string) => (
          <Badge key={s} value={s} />
        ))}
      </div>
      <Table columns={['Transition', 'Gate', 'Preconditions', 'Cascades', 'Roles']}>
        {machine.transitions.map((t: any, i: number) => (
          <tr key={i} className="hover:bg-surface-sunken/60">
            <td className="table-cell whitespace-nowrap">
              <div className="flex items-center gap-1.5">
                <Badge value={t.source === '*' ? 'any' : t.source} />
                <ArrowRight className="h-3 w-3 text-ink-faint" />
                <Badge value={t.target} />
              </div>
            </td>
            <td className="table-cell mono whitespace-nowrap text-ink-muted">{t.gate}</td>
            <td className="table-cell">
              {t.preconditions.length === 0 ? (
                <span className="text-xs text-ink-faint">none</span>
              ) : (
                <ul className="space-y-1">
                  {t.preconditions.map((p: any) => (
                    <li key={p.id} className="text-xs">
                      <span className="mono rounded bg-surface-sunken px-1 py-0.5 text-ink">
                        {p.id}
                      </span>{' '}
                      <span className="text-ink-muted">{p.name}</span>
                    </li>
                  ))}
                </ul>
              )}
            </td>
            <td className="table-cell">
              {t.cascades.length === 0 ? (
                <span className="text-xs text-ink-faint">—</span>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {t.cascades.map((c: string) => (
                    <span key={c} className="mono rounded bg-surface-sunken px-1.5 py-0.5 text-ink-muted">
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </td>
            <td className="table-cell text-xs text-ink-muted">
              {t.roles.length ? t.roles.map(label).join(', ') : 'any'}
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}
