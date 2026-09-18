import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, ArrowUpRight, Plus, ShieldCheck } from 'lucide-react'
import { api, ApiError, getStoredUser } from '../lib/api'
import { PageHeader } from '../components/Layout'
import {
  Badge,
  Card,
  Empty,
  Field,
  Modal,
  PageLoader,
  Tabs,
  useToast,
} from '../components/ui'
import { GatePanel, InvariantList } from '../components/governance'
import { cx, formatDate, formatDateTime, label } from '../lib/format'

export default function ThreatModelDetail() {
  const { id = '' } = useParams()
  const me = getStoredUser()
  const [tm, setTm] = useState<any>(null)
  const [ref, setRef] = useState<any>(null)
  const [deployments, setDeployments] = useState<any[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [tab, setTab] = useState('scenarios')
  const [busy, setBusy] = useState<string | null>(null)
  const [modal, setModal] = useState<any>(null)
  const { push } = useToast()

  const load = useCallback(() => api.get<any>(`/threat-models/${id}`).then(setTm), [id])

  useEffect(() => {
    load().catch(() => undefined)
    api.get('/threat-models/reference-data').then(setRef).catch(() => undefined)
    api.get<any[]>('/users').then(setUsers).catch(() => undefined)
    api
      .get<any[]>('/controls')
      .then(async (objectives) => {
        const details = await Promise.all(
          objectives.map((o) => api.get<any>(`/controls/${o.id}`).catch(() => null)),
        )
        setDeployments(
          details
            .filter(Boolean)
            .flatMap((o: any) =>
              o.activities.flatMap((a: any) =>
                a.deployments.map((d: any) => ({ ...d, objective: o.reference })),
              ),
            ),
        )
      })
      .catch(() => undefined)
  }, [load])

  const fail = (err: unknown, title = 'Refused') =>
    err instanceof ApiError
      ? push({ kind: 'error', title, body: err.message, rule: err.rule })
      : push({ kind: 'error', title, body: String(err) })

  const run = async (key: string, fn: () => Promise<unknown>, okTitle: string, okBody?: string) => {
    setBusy(key)
    try {
      await fn()
      await load()
      push({ kind: 'ok', title: okTitle, body: okBody })
      return true
    } catch (err) {
      fail(err)
      return false
    } finally {
      setBusy(null)
    }
  }

  const transition = async (target: string, reason?: string) => {
    setBusy(target)
    try {
      const res = await api.post<any>(`/threat-models/${id}/transition`, { target, reason })
      setTm(res.model)
      push({ kind: 'ok', title: `Model moved to ${label(target)}` })
    } catch (err) {
      fail(err, 'Transition blocked')
    } finally {
      setBusy(null)
    }
  }

  if (!tm) return <PageLoader />

  const userName = (uid: string | null) => users.find((u) => u.id === uid)?.full_name ?? '—'

  return (
    <>
      <Link
        to="/threat-models"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" />
        Threat models
      </Link>

      <PageHeader
        eyebrow={tm.reference}
        title={tm.title}
        description={tm.description}
        meta={
          <>
            <Badge value={tm.lifecycle_state} />
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              {tm.asset_name}
            </span>
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              {tm.methodology}
            </span>
            {tm.fully_signed_off && (
              <span className="chip border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300">
                <ShieldCheck className="h-3 w-3" />
                Dual sign-off
              </span>
            )}
          </>
        }
      />

      {tm.signoff_stripped_reason && (
        <div className="mb-5 flex gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/40">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
              Sign-off stripped
            </p>
            <p className="mt-0.5 text-sm text-amber-800 dark:text-amber-300">
              {tm.signoff_stripped_reason}
            </p>
          </div>
        </div>
      )}

      <div className="mb-5">
        <Tabs
          tabs={[
            { id: 'scenarios', label: 'Scenarios', count: tm.scenarios.length },
            { id: 'components', label: 'Components', count: tm.components.length },
            { id: 'lifecycle', label: 'Lifecycle and sign-off' },
            { id: 'invariants', label: 'Invariants', count: tm.invariants.length },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'scenarios' && (
        <Card
          title="Threat scenarios"
          subtitle="Every scenario must resolve to mitigation, a local Low acceptance, or promotion to the risk register (TINV-1). Nothing may remain Identified once the model is Active."
          action={
            <button
              className="btn-ghost btn-sm"
              onClick={() => setModal({ type: 'scenario' })}
              disabled={tm.components.length === 0}
            >
              <Plus className="h-3.5 w-3.5" />
              Scenario
            </button>
          }
          bodyClassName={tm.scenarios.length ? 'p-0' : undefined}
        >
          {tm.scenarios.length === 0 ? (
            <Empty
              title="No scenarios identified"
              hint={
                tm.components.length === 0
                  ? 'Decompose the system into components first.'
                  : 'Identify threats against the decomposed components.'
              }
            />
          ) : (
            <ul className="divide-y">
              {tm.scenarios.map((s: any) => (
                <li key={s.id} className="px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="mono text-ink-faint">{s.reference}</span>
                    <Badge value={s.category} />
                    <Badge value={s.inherent_severity} />
                    <Badge value={s.status} />
                    <span className="ml-auto text-xs text-ink-muted">
                      on {s.component_name}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-ink">{s.description}</p>

                  {s.reopened_reason && (
                    <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                      Re-opened {formatDate(s.reopened_at)}: {s.reopened_reason}
                    </p>
                  )}

                  {s.mitigations.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {s.mitigations.map((m: any) => (
                        <li
                          key={m.link_id}
                          className={cx(
                            'flex flex-wrap items-center gap-2 rounded-md border px-3 py-1.5 text-xs',
                            m.live
                              ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20'
                              : 'border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/30',
                          )}
                        >
                          <span className="mono">{m.deployment_reference}</span>
                          <span className="text-ink-muted">{m.asset}</span>
                          <Badge value={m.deployment_status} />
                          <span className="text-ink-faint">
                            {label(m.effectiveness_assurance)}
                          </span>
                          {!m.live && (
                            <span className="ml-auto font-medium text-rose-700 dark:text-rose-300">
                              not operating — does not mitigate (TINV-4)
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}

                  {s.promoted_risk_id && (
                    <Link
                      to={`/risks/${s.promoted_risk_id}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent"
                    >
                      <ArrowUpRight className="h-3.5 w-3.5" />
                      Promoted to the risk register
                    </Link>
                  )}

                  {s.status === 'Identified' && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setModal({ type: 'mitigate', scenario: s })}
                      >
                        Link a mitigating control
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        disabled={s.requires_promotion}
                        title={
                          s.requires_promotion
                            ? 'TINV-3: a Medium or above scenario cannot be accepted locally'
                            : undefined
                        }
                        onClick={() => setModal({ type: 'accept', scenario: s })}
                      >
                        Accept locally
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setModal({ type: 'promote', scenario: s })}
                      >
                        Promote to risk register
                      </button>
                    </div>
                  )}

                  {s.status === 'Accepted' && (
                    <p className="mt-2 text-xs text-ink-muted">
                      Accepted until {formatDate(s.acceptance_expiry)} — {s.acceptance_rationale}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'components' && (
        <Card
          title="Data flow components"
          subtitle="Processes, datastores, external entities, flows and trust boundaries."
          action={
            <button className="btn-ghost btn-sm" onClick={() => setModal({ type: 'component' })}>
              <Plus className="h-3.5 w-3.5" />
              Component
            </button>
          }
          bodyClassName={tm.components.length ? 'p-0' : undefined}
        >
          {tm.components.length === 0 ? (
            <Empty title="No components defined" />
          ) : (
            <ul className="divide-y">
              {tm.components.map((c: any) => (
                <li key={c.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{c.name}</p>
                    {c.description && (
                      <p className="mt-0.5 text-sm text-ink-muted">{c.description}</p>
                    )}
                  </div>
                  <Badge value={c.component_type} />
                  <span className="text-xs tabular-nums text-ink-faint">
                    {c.scenario_count} scenario{c.scenario_count === 1 ? '' : 's'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'lifecycle' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Available transitions"
            subtitle="Review to Active is where TINV-1 and TINV-2 land together: every scenario resolved, and two independent signatures."
          >
            <GatePanel
              gates={tm.gates}
              onFire={transition}
              busy={busy}
              reasonPrompt={(t) => ['Deprecated', 'Abandoned'].includes(t)}
            />
          </Card>

          <Card
            title="Sign-off"
            subtitle="TINV-2: AppSec sign-off is satisfied by team membership. The System Owner signature is personal, and the two cannot be the same person."
          >
            <div className="space-y-3">
              <SignoffRow
                title="AppSec sign-off"
                who={tm.appsec_signoff_by ? userName(tm.appsec_signoff_by) : null}
                when={tm.appsec_signoff_at}
                hint="Requires AppSec_Lead or AppSec_Engineer, and cannot be the System Owner."
                canSign={
                  !!me?.roles.some((r) => r.startsWith('AppSec') || r === 'Admin') &&
                  me?.id !== tm.system_owner_id
                }
                busy={busy === 'appsec'}
                onSign={() =>
                  run(
                    'appsec',
                    () => api.post(`/threat-models/${id}/signoff`, { as_role: 'appsec' }),
                    'AppSec sign-off recorded',
                  )
                }
              />
              <SignoffRow
                title="System Owner sign-off"
                who={tm.owner_signoff_by ? userName(tm.owner_signoff_by) : null}
                when={tm.owner_signoff_at}
                hint={`Only ${userName(tm.system_owner_id)} can sign this.`}
                canSign={me?.id === tm.system_owner_id || !!me?.roles.includes('Admin')}
                busy={busy === 'owner'}
                onSign={() =>
                  run(
                    'owner',
                    () => api.post(`/threat-models/${id}/signoff`, { as_role: 'owner' }),
                    'System Owner sign-off recorded',
                  )
                }
              />
            </div>
          </Card>
        </div>
      )}

      {tab === 'invariants' && (
        <Card title="Invariants on this model">
          <InvariantList invariants={tm.invariants} />
        </Card>
      )}

      {/* modals */}
      <Modal
        open={modal?.type === 'component'}
        onClose={() => setModal(null)}
        title="New component"
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            const f = new FormData(e.target as HTMLFormElement)
            const ok = await run(
              'component',
              () =>
                api.post(`/threat-models/${id}/components`, {
                  name: f.get('name'),
                  component_type: f.get('component_type'),
                  description: f.get('description') || null,
                }),
              'Component added',
            )
            if (ok) setModal(null)
          }}
        >
          <Field label="Name">
            <input className="field" name="name" required />
          </Field>
          <Field label="Type">
            <select className="field" name="component_type">
              {(ref?.component_types ?? []).map((t: string) => (
                <option key={t} value={t}>
                  {label(t)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Description">
            <textarea className="field" name="description" rows={2} />
          </Field>
          <div className="flex justify-end border-t pt-4">
            <button className="btn-primary">Add component</button>
          </div>
        </form>
      </Modal>

      <Modal
        open={modal?.type === 'scenario'}
        onClose={() => setModal(null)}
        title="New threat scenario"
        description="Severity determines what resolutions are legal. Medium and above cannot be accepted locally (TINV-3)."
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            const f = new FormData(e.target as HTMLFormElement)
            const ok = await run(
              'scenario',
              () =>
                api.post(`/threat-models/${id}/scenarios`, {
                  component_id: f.get('component_id'),
                  category: f.get('category'),
                  description: f.get('description'),
                  inherent_severity: f.get('inherent_severity'),
                }),
              'Scenario added',
            )
            if (ok) setModal(null)
          }}
        >
          <Field label="Component">
            <select className="field" name="component_id">
              {tm.components.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({label(c.component_type)})
                </option>
              ))}
            </select>
          </Field>
          <Field label="STRIDE category">
            <select className="field" name="category">
              {(ref?.stride_categories ?? []).map((c: string) => (
                <option key={c} value={c}>
                  {label(c)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Description">
            <textarea className="field" name="description" rows={3} required />
          </Field>
          <Field label="Inherent severity">
            <select className="field" name="inherent_severity" defaultValue="Medium">
              {(ref?.severities ?? []).map((s: string) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <div className="flex justify-end border-t pt-4">
            <button className="btn-primary">Add scenario</button>
          </div>
        </form>
      </Modal>

      <Modal
        open={modal?.type === 'mitigate'}
        onClose={() => setModal(null)}
        wide
        title="Link a mitigating control deployment"
        description="TINV-4: only a deployment that is Active or Degraded can mitigate a threat. A planned or failed control does not."
      >
        <ul className="max-h-96 space-y-1 overflow-y-auto">
          {deployments.map((d) => {
            const live = ['Active', 'Degraded'].includes(d.deployment_status)
            return (
              <li key={d.id}>
                <button
                  disabled={!live}
                  className={cx(
                    'flex w-full flex-wrap items-center gap-2 rounded-lg border px-3 py-2.5 text-left',
                    live
                      ? 'bg-surface-sunken hover:border-accent'
                      : 'cursor-not-allowed border-dashed opacity-55',
                  )}
                  onClick={async () => {
                    const ok = await run(
                      'mitigate',
                      () =>
                        api.post(
                          `/threat-models/${id}/scenarios/${modal.scenario.id}/mitigate`,
                          { deployment_id: d.id, effectiveness_assurance: 'Fully_Mitigated' },
                        ),
                      'Scenario mitigated',
                    )
                    if (ok) setModal(null)
                  }}
                >
                  <span className="mono text-ink-faint">{d.objective}</span>
                  <span className="mono text-ink-faint">{d.reference}</span>
                  <span className="text-sm text-ink">{d.asset_name}</span>
                  <Badge value={d.deployment_status} />
                  <Badge value={d.ce_rating} />
                  {!live && (
                    <span className="ml-auto text-xs text-ink-faint">not operating</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      </Modal>

      <Modal
        open={modal?.type === 'accept'}
        onClose={() => setModal(null)}
        title="Accept locally"
        description="TINV-5: a local acceptance runs for at most 12 months and always carries an expiry."
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            const f = new FormData(e.target as HTMLFormElement)
            const ok = await run(
              'accept',
              () =>
                api.post(`/threat-models/${id}/scenarios/${modal.scenario.id}/accept`, {
                  acceptance_expiry: f.get('acceptance_expiry'),
                  acceptance_rationale: f.get('acceptance_rationale'),
                }),
              'Scenario accepted',
            )
            if (ok) setModal(null)
          }}
        >
          <Field label="Acceptance expiry">
            <input className="field" type="date" name="acceptance_expiry" required />
          </Field>
          <Field label="Rationale">
            <textarea className="field" name="acceptance_rationale" rows={3} required />
          </Field>
          <div className="flex justify-end border-t pt-4">
            <button className="btn-primary">Accept</button>
          </div>
        </form>
      </Modal>

      <Modal
        open={modal?.type === 'promote'}
        onClose={() => setModal(null)}
        wide
        title="Promote to the risk register"
        description="Creates a real risk record at Intake, pre-filled from the scenario and linked back to it. This is the bidirectional link between threat modelling and GRC."
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            const f = new FormData(e.target as HTMLFormElement)
            setBusy('promote')
            try {
              const res = await api.post<any>(
                `/threat-models/${id}/scenarios/${modal.scenario.id}/promote`,
                {
                  tier: f.get('tier'),
                  risk_owner_id: f.get('risk_owner_id') || null,
                  risk_stakeholder_id: f.get('risk_stakeholder_id') || null,
                },
              )
              setTm(res.model)
              setModal(null)
              push({
                kind: 'ok',
                title: `Promoted to ${res.promoted_risk.reference}`,
                body: 'A risk record was created at Intake and linked to this scenario.',
              })
            } catch (err) {
              fail(err)
            } finally {
              setBusy(null)
            }
          }}
        >
          <p className="rounded-lg border bg-surface-sunken px-3 py-2.5 text-sm text-ink-muted">
            {modal?.scenario?.description}
          </p>
          <Field label="Risk tier">
            <select className="field" name="tier" defaultValue="Tier_3">
              {['Tier_1', 'Tier_2', 'Tier_3', 'Tier_4'].map((t) => (
                <option key={t} value={t}>
                  {label(t)}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Risk owner">
              <select className="field" name="risk_owner_id">
                <option value="">Assign later</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Risk stakeholder">
              <select className="field" name="risk_stakeholder_id">
                <option value="">Assign later</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="flex justify-end border-t pt-4">
            <button className="btn-primary" disabled={busy === 'promote'}>
              Create risk record
            </button>
          </div>
        </form>
      </Modal>
    </>
  )
}

function SignoffRow({
  title,
  who,
  when,
  hint,
  canSign,
  busy,
  onSign,
}: {
  title: string
  who: string | null
  when: string | null
  hint: string
  canSign: boolean
  busy: boolean
  onSign: () => void
}) {
  return (
    <div
      className={cx(
        'rounded-lg border p-4',
        who
          ? 'border-emerald-300 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20'
          : 'bg-surface-sunken',
      )}
    >
      <div className="flex items-center gap-2">
        <ShieldCheck className={cx('h-4 w-4', who ? 'text-emerald-600' : 'text-ink-faint')} />
        <p className="text-sm font-semibold text-ink">{title}</p>
      </div>
      {who ? (
        <p className="mt-1.5 text-sm text-ink">
          {who} · {formatDateTime(when)}
        </p>
      ) : (
        <>
          <p className="mt-1.5 text-xs text-ink-muted">{hint}</p>
          <button
            className="btn-primary btn-sm mt-3"
            disabled={!canSign || busy}
            onClick={onSign}
          >
            Sign off
          </button>
        </>
      )}
    </div>
  )
}
