import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Lock, ShieldQuestion } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Card, Field, Modal, PageLoader, Table, useToast } from '../components/ui'
import { cx, label } from '../lib/format'

type Framework = {
  id: string
  framework_id: string
  name: string
  version: string
  authority: string | null
  adopted: boolean
  redistributable: boolean
  licence_note: string | null
  source_url: string | null
  requirements: number
}

type Link = {
  link_id: string
  objective_id: string
  reference: string | null
  title: string | null
  lifecycle_state: string | null
  coverage_level: string
  satisfies: boolean
  rationale: string | null
}

type Requirement = {
  id: string
  ref: string
  title: string
  requirement_text: string | null
  category: string | null
  state: string
  rationale: string | null
  gap_reason: string | null
  compensating_expiry: string | null
  links: Link[]
}

type Posture = {
  framework_id: string
  name: string
  version: string
  requirements: number
  counts: Record<string, number>
  in_scope: number
  satisfied: number
  coverage_pct: number | null
  scope_declared: boolean
  scoped_assets: { id: string; name: string }[]
}

const STATE_TONE: Record<string, string> = {
  Covered: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300',
  Compensating: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300',
  Gap: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300',
  Not_Applicable: 'border-border bg-surface-sunken text-ink-muted',
  Applicable: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300',
}

export default function Compliance() {
  const [frameworks, setFrameworks] = useState<Framework[] | null>(null)
  const [licensed, setLicensed] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [requirements, setRequirements] = useState<Requirement[] | null>(null)
  const [posture, setPosture] = useState<Posture[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [active, setActive] = useState<Requirement | null>(null)
  const { push } = useToast()

  const loadFrameworks = () =>
    api
      .get<{ frameworks: Framework[]; licensed_frameworks: string[] }>('/compliance/frameworks')
      .then((d) => {
        setFrameworks(d.frameworks)
        setLicensed(d.licensed_frameworks)
        setSelected((s) => s ?? d.frameworks.find((f) => f.adopted)?.framework_id ?? null)
      })

  const loadPosture = () =>
    api.get<{ frameworks: Posture[] }>('/compliance/posture').then((d) => setPosture(d.frameworks))

  const loadRequirements = (id: string) =>
    api
      .get<{ requirements: Requirement[] }>(`/compliance/frameworks/${id}/requirements`)
      .then((d) => setRequirements(d.requirements))

  useEffect(() => {
    loadFrameworks().catch(() => undefined)
    loadPosture().catch(() => undefined)
  }, [])

  useEffect(() => {
    if (selected) {
      setRequirements(null)
      loadRequirements(selected).catch(() => undefined)
    }
  }, [selected])

  const current = posture.find((p) => p.framework_id === selected)

  const shown = useMemo(() => {
    if (!requirements) return []
    if (filter === 'all') return requirements
    if (filter === 'open') {
      return requirements.filter((r) => r.state !== 'Covered' && r.state !== 'Not_Applicable')
    }
    return requirements.filter((r) => r.state === filter)
  }, [requirements, filter])

  const assess = async (requirement: Requirement, target: string, rationale?: string) => {
    try {
      await api.post(`/compliance/requirements/${requirement.id}/assess`, {
        target,
        ...(rationale ? { rationale } : {}),
      })
      push({ kind: 'ok', title: `${requirement.ref} → ${label(target)}` })
      if (selected) await loadRequirements(selected)
      await loadPosture()
      setActive(null)
    } catch (err) {
      if (err instanceof ApiError) {
        push({
          kind: 'error',
          title: err.rule ? `Blocked by ${err.rule}` : 'Blocked',
          body: err.message,
          rule: err.rule,
        })
      }
    }
  }

  if (!frameworks) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Compliance"
        description="Requirements are records, not framework names. A requirement is Covered only while a control that satisfies it is Operating and deployed where the requirement applies (AINV-2), so the figure moves when a control fails rather than when somebody remembers to revisit it."
      />

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <Card title="Frameworks" bodyClassName="p-0">
            <ul className="divide-y divide-border">
              {frameworks.map((f) => (
                <li key={f.id}>
                  <button
                    onClick={() => setSelected(f.framework_id)}
                    className={cx(
                      'flex w-full flex-col items-start gap-1 px-4 py-3 text-left transition',
                      selected === f.framework_id ? 'bg-surface-sunken' : 'hover:bg-surface-sunken/60',
                    )}
                  >
                    <span className="flex w-full items-center justify-between gap-2">
                      <span className="font-medium text-ink">{f.name}</span>
                      {f.adopted ? (
                        <span className="chip border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300">
                          Adopted
                        </span>
                      ) : (
                        <span className="chip">Reference</span>
                      )}
                    </span>
                    <span className="text-xs text-ink-muted">
                      v{f.version} · {f.requirements} requirements
                    </span>
                    {!f.redistributable && (
                      <span className="mt-1 inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
                        <Lock className="h-3 w-3" />
                        Licensed: load from your own copy
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {licensed.length > 0 && (
            <Card title="Why some catalogues are empty">
              <p className="text-sm text-ink-muted">
                {licensed.join(', ')} are copyrighted and cannot be redistributed by this
                repository. Their framework records ship with no requirement text, and the loader
                refuses at boot any catalogue that carries text it may not distribute (AINV-6).
              </p>
              <p className="mt-2 text-sm text-ink-muted">
                Load them from your own licensed copy with{' '}
                <code className="mono text-xs">tools/import_framework.py</code>, which writes to
                the database and never back into the repository.
              </p>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {current && (
            <Card>
              <div className="flex flex-wrap items-end gap-6">
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-faint">Coverage</p>
                  <p className="text-3xl font-semibold text-ink">
                    {current.coverage_pct === null ? '—' : `${current.coverage_pct}%`}
                  </p>
                  <p className="text-xs text-ink-muted">
                    {current.satisfied} of {current.in_scope} in scope
                  </p>
                </div>
                {(['Covered', 'Compensating', 'Gap', 'Applicable', 'Not_Applicable', 'Not_Assessed'] as const).map(
                  (state) => (
                    <div key={state}>
                      <p className="text-xs uppercase tracking-wide text-ink-faint">
                        {label(state)}
                      </p>
                      <p className="text-xl font-semibold text-ink">{current.counts[state] ?? 0}</p>
                    </div>
                  ),
                )}
              </div>

              {!current.scope_declared && (
                <p className="mt-4 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    No asset declares itself in this framework's scope, so no requirement can
                    reach Covered (AINV-9). A percentage over an undeclared scope would be a
                    confident number about an estate nobody assessed, so none is shown.
                  </span>
                </p>
              )}
              {current.scope_declared && (
                <p className="mt-3 text-xs text-ink-muted">
                  In scope: {current.scoped_assets.map((a) => a.name).join(', ')}
                </p>
              )}
            </Card>
          )}

          <Card bodyClassName="p-0">
            <div className="flex flex-wrap gap-2 border-b border-border px-4 py-3">
              {['all', 'open', 'Covered', 'Gap', 'Compensating', 'Not_Applicable'].map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cx('chip', filter === f && 'border-accent text-accent')}
                >
                  {f === 'all' ? 'All' : f === 'open' ? 'Open' : label(f)}
                </button>
              ))}
            </div>

            {!requirements ? (
              <PageLoader />
            ) : (
              <Table columns={['Requirement', 'State', 'Controls', '']}>
                {shown.map((r) => (
                  <tr key={r.id} className="group hover:bg-surface-sunken/60">
                    <td className="table-cell">
                      <span className="mono text-ink-faint">{r.ref}</span>
                      <p className="mt-0.5 font-medium text-ink">{r.title}</p>
                      {r.category && (
                        <span className="mt-1 inline-block text-xs text-ink-muted">
                          {r.category}
                        </span>
                      )}
                      {r.gap_reason && (
                        <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">
                          {r.gap_reason}
                        </p>
                      )}
                      {r.rationale && r.state === 'Not_Applicable' && (
                        <p className="mt-1 text-xs text-ink-muted">Excluded: {r.rationale}</p>
                      )}
                    </td>
                    <td className="table-cell">
                      <span className={cx('chip', STATE_TONE[r.state] ?? '')}>
                        {label(r.state)}
                      </span>
                      {r.compensating_expiry && (
                        <p className="mt-1 text-xs text-ink-muted">
                          expires {r.compensating_expiry}
                        </p>
                      )}
                    </td>
                    <td className="table-cell">
                      {r.links.length === 0 ? (
                        <span className="text-xs text-ink-faint">none</span>
                      ) : (
                        <ul className="space-y-1">
                          {r.links.map((link) => (
                            <li key={link.link_id} className="text-xs">
                              <span className="mono text-ink-faint">{link.reference}</span>{' '}
                              <span
                                className={cx(
                                  'chip',
                                  !link.satisfies &&
                                    'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300',
                                )}
                              >
                                {label(link.coverage_level)}
                              </span>
                              {!link.satisfies && (
                                <span className="ml-1 text-ink-muted">does not satisfy</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className="table-cell text-right">
                      <button className="btn-ghost" onClick={() => setActive(r)}>
                        Assess
                      </button>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>
      </div>

      {active && (
        <AssessModal
          requirement={active}
          onClose={() => setActive(null)}
          onAssess={assess}
        />
      )}
    </>
  )
}

function AssessModal({
  requirement,
  onClose,
  onAssess,
}: {
  requirement: Requirement
  onClose: () => void
  onAssess: (r: Requirement, target: string, rationale?: string) => void
}) {
  const [target, setTarget] = useState('Applicable')
  const [rationale, setRationale] = useState('')

  const needsRationale = target === 'Not_Applicable' || target === 'Compensating'

  return (
    <Modal open title={`${requirement.ref} — ${requirement.title}`} onClose={onClose}>
      {requirement.requirement_text && (
        <p className="mb-4 rounded-md bg-surface-sunken p-3 text-sm text-ink-muted">
          {requirement.requirement_text}
        </p>
      )}

      <Field label="Position">
        <select
          className="field"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        >
          <option value="Applicable">Applicable — in scope, coverage not established</option>
          <option value="Covered">Covered — a live control satisfies it</option>
          <option value="Compensating">Compensating — time-bound interim position</option>
          <option value="Gap">Gap — applicable and not covered</option>
          <option value="Not_Applicable">Not applicable — excluded from scope</option>
        </select>
      </Field>

      {needsRationale && (
        <Field
          className="mt-4"
          label="Justification"
          hint={
            target === 'Not_Applicable'
              ? 'Required. An unexplained exclusion is the most common finding raised against a Statement of Applicability (AINV-1).'
              : 'Required. Say what is being compensated for, and why the compensation is adequate.'
          }
        >
          <textarea
            className="field min-h-24"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
        </Field>
      )}

      <p className="mt-3 flex items-start gap-2 text-xs text-ink-muted">
        <ShieldQuestion className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Covered is gated. It needs a control objective that is Operating with a live deployment
          inside this framework's scope, and a link asserting full coverage. A Partial link does
          not satisfy.
        </span>
      </p>

      <div className="mt-5 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn-primary"
          disabled={needsRationale && rationale.trim().length === 0}
          onClick={() => onAssess(requirement, target, rationale.trim() || undefined)}
        >
          Record position
        </button>
      </div>
    </Modal>
  )
}
