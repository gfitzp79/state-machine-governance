import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, FlaskConical, Plus, ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { PersonSelect, peopleWithRole } from '../components/people'
import {
  Badge,
  Card,
  Detail,
  Empty,
  Field,
  Modal,
  PageLoader,
  Tabs,
  useToast,
} from '../components/ui'
import { CEResolution, GatePanel, InvariantList } from '../components/governance'
import { cx, formatDate, formatDateTime, label } from '../lib/format'

export default function ControlDetail() {
  const { id = '' } = useParams()
  const [ctl, setCtl] = useState<any>(null)
  const [assets, setAssets] = useState<any[]>([])
  const [ref, setRef] = useState<any>(null)
  const [users, setUsers] = useState<any[]>([])
  const [tab, setTab] = useState('structure')
  const [busy, setBusy] = useState<string | null>(null)
  const [modal, setModal] = useState<any>(null)
  const [deployment, setDeployment] = useState<any>(null)
  const { push } = useToast()

  const load = useCallback(() => api.get<any>(`/controls/${id}`).then(setCtl), [id])

  useEffect(() => {
    load().catch(() => undefined)
    api.get<any[]>('/assets').then(setAssets).catch(() => undefined)
    api.get('/controls/reference-data').then(setRef).catch(() => undefined)
    // CINV-15 refuses an operator who does not hold the role, so the picker
    // asks for exactly the set the write will accept.
    peopleWithRole('Control_Operator').then(setUsers).catch(() => undefined)
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
      if (deployment) {
        const fresh = await api.get<any>(`/controls/deployments/${deployment.id}`)
        setDeployment(fresh)
      }
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
      const res = await api.post<any>(`/controls/${id}/transition`, { target, reason })
      setCtl(res.objective)
      const effects: any[] = res.transition.cascades ?? []
      push({
        kind: effects.length ? 'info' : 'ok',
        title: `Control moved to ${label(target)}`,
        body: effects.length
          ? `${effects.length} cascade effect${effects.length === 1 ? '' : 's'}: ${effects.map((e) => e.description).join('; ')}`
          : undefined,
      })
    } catch (err) {
      fail(err, 'Transition blocked')
    } finally {
      setBusy(null)
    }
  }

  if (!ctl) return <PageLoader />

  const deployments = ctl.activities.flatMap((a: any) =>
    a.deployments.map((d: any) => ({ ...d, activity: a })),
  )

  return (
    <>
      <Link
        to="/controls"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" />
        Control library
      </Link>

      <PageHeader
        eyebrow={ctl.reference}
        title={ctl.title}
        description={ctl.description}
        meta={
          <>
            <Badge value={ctl.lifecycle_state} />
            <Badge value={ctl.effective_ce}>Effective {ctl.effective_ce}</Badge>
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              {label(ctl.family)}
            </span>
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              {ctl.control_type}
            </span>
            <span
              className={cx(
                'chip',
                ctl.contributes_to_scoring
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                  : 'border-line bg-surface-sunken text-ink-faint',
              )}
            >
              {ctl.contributes_to_scoring
                ? 'Contributes to risk scoring'
                : 'Excluded from risk scoring (CE-5)'}
            </span>
          </>
        }
      />

      {ctl.lifecycle_state === 'Failure' && (
        <div className="mb-5 flex gap-3 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 dark:border-rose-900 dark:bg-rose-950/40">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
          <div>
            <p className="text-sm font-medium text-rose-900 dark:text-rose-200">
              This control is in Failure
            </p>
            <p className="mt-0.5 text-sm text-rose-800 dark:text-rose-300">
              Residual scores are frozen on every linked risk (CINV-5), and every threat scenario
              it was mitigating has re-opened (TINV-4). Record a remediation plan before returning
              it to Operating; escalation to the CISO is automatic after 15 business days.
            </p>
          </div>
        </div>
      )}

      <div className="mb-5">
        <Tabs
          tabs={[
            { id: 'structure', label: 'Structure', count: deployments.length },
            { id: 'lifecycle', label: 'Lifecycle' },
            { id: 'scoring', label: 'Scoring contribution' },
            { id: 'impact', label: 'Linked records', count: ctl.linked_risks.length + ctl.linked_policies.length },
            { id: 'invariants', label: 'Invariants', count: ctl.invariants.length },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'structure' && (
        <div className="space-y-4">
          <Card
            title="Activities and deployments"
            subtitle="An activity is how the objective is implemented. A deployment is where it actually runs, and carries its own effectiveness rating."
            action={
              <button className="btn-ghost btn-sm" onClick={() => setModal({ type: 'activity' })}>
                <Plus className="h-3.5 w-3.5" />
                Activity
              </button>
            }
            bodyClassName={ctl.activities.length ? 'p-0' : undefined}
          >
            {ctl.activities.length === 0 ? (
              <Empty
                title="No activities defined"
                hint="A control cannot leave Design without at least one activity and a deployment plan."
              />
            ) : (
              <ul className="divide-y">
                {ctl.activities.map((a: any) => (
                  <li key={a.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="mono text-ink-faint">{a.reference}</span>
                      <span className="font-medium text-ink">{a.title}</span>
                      <Badge value={a.lifecycle_state} />
                      <div className="ml-auto flex gap-1.5">
                        <button
                          className="btn-ghost btn-sm"
                          onClick={() => setModal({ type: 'activity-transition', activity: a })}
                        >
                          Transition
                        </button>
                        <button
                          className="btn-ghost btn-sm"
                          onClick={() => setModal({ type: 'deployment', activity: a })}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          Deploy
                        </button>
                      </div>
                    </div>
                    {a.description && (
                      <p className="mt-1 text-sm text-ink-muted">{a.description}</p>
                    )}

                    {a.deployments.length === 0 ? (
                      <p className="mt-3 rounded-md border border-dashed px-3 py-2 text-xs text-ink-faint">
                        No deployments. A control objective cannot reach Operating without at
                        least one Active deployment (OL-4).
                      </p>
                    ) : (
                      <ul className="mt-3 space-y-1.5">
                        {a.deployments.map((d: any) => (
                          <li key={d.id}>
                            <button
                              className="flex w-full flex-wrap items-center gap-2 rounded-lg border bg-surface-sunken px-3 py-2.5 text-left hover:border-accent"
                              onClick={async () => {
                                const detail = await api.get<any>(
                                  `/controls/deployments/${d.id}`,
                                )
                                setDeployment(detail)
                              }}
                            >
                              <span className="mono text-ink-faint">{d.reference}</span>
                              <span className="text-sm text-ink">{d.asset_name}</span>
                              <Badge value={d.deployment_status} />
                              <Badge value={d.ce_rating} />
                              {d.ce_expired && d.ce_rating !== 'CE-Unvalidated' && (
                                <span className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300">
                                  evidence expired
                                </span>
                              )}
                              <span className="ml-auto text-xs text-ink-faint">
                                {d.test_frequency} · last {label(d.last_test_result)} ·{' '}
                                {d.test_count} test{d.test_count === 1 ? '' : 's'}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'lifecycle' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Available transitions"
            subtitle="Retirement is blocked while a linked risk is above appetite and unmitigated (CINV-8)."
          >
            <GatePanel
              gates={ctl.gates}
              onFire={transition}
              busy={busy}
              reasonPrompt={(t) => t === 'Deprecated'}
            />
          </Card>
          <Card title="Control record">
            <dl className="divide-y">
              <Detail label="Remediation plan">
                <textarea
                  className="field"
                  rows={3}
                  defaultValue={ctl.remediation_plan ?? ''}
                  placeholder="Required before a failed control can return to Operating"
                  onBlur={(e) =>
                    e.target.value !== (ctl.remediation_plan ?? '') &&
                    run(
                      'patch',
                      () => api.patch(`/controls/${id}`, { remediation_plan: e.target.value }),
                      'Remediation plan saved',
                    )
                  }
                />
              </Detail>
              <Detail label="Retirement rationale">
                <textarea
                  className="field"
                  rows={2}
                  defaultValue={ctl.deprecation_rationale ?? ''}
                  placeholder="Required to retire this control"
                  onBlur={(e) =>
                    e.target.value !== (ctl.deprecation_rationale ?? '') &&
                    run(
                      'patch',
                      () =>
                        api.patch(`/controls/${id}`, { deprecation_rationale: e.target.value }),
                      'Rationale saved',
                    )
                  }
                />
              </Detail>
              <Detail label="Control owner">
                <PersonSelect
                  label=""
                  role="Control_Owner"
                  value={ctl.control_owner_id}
                  onChange={(owner) =>
                    run(
                      'patch',
                      () => api.patch(`/controls/${id}`, { control_owner_id: owner }),
                      'Owner updated',
                    )
                  }
                />
              </Detail>
            </dl>
          </Card>
        </div>
      )}

      {tab === 'scoring' && (
        <Card
          title="How this control feeds risk scoring"
          subtitle="Worst-case effectiveness across qualifying deployments, never an average and never best case (CINV-6)."
        >
          <CEResolution data={ctl.ce_resolution} />
        </Card>
      )}

      {tab === 'impact' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Linked risks"
            subtitle="Retiring this control is blocked while any of these is above appetite and unmitigated."
            bodyClassName={ctl.linked_risks.length ? 'p-0' : undefined}
          >
            {ctl.linked_risks.length === 0 ? (
              <Empty title="No risks linked" />
            ) : (
              <ul className="divide-y">
                {ctl.linked_risks.map((r: any) => (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <Link to={`/risks/${r.id}`} className="mono text-ink-faint hover:text-accent">
                        {r.reference}
                      </Link>
                      <p className="truncate text-sm text-ink">{r.title}</p>
                    </div>
                    <Badge value={r.reported_rating} />
                    <Badge value={r.lifecycle_state} />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Linked policies"
            subtitle="A policy revision starts a 30-day alignment obligation on this control (PINV-7)."
            bodyClassName={ctl.linked_policies.length ? 'p-0' : undefined}
          >
            {ctl.linked_policies.length === 0 ? (
              <Empty title="No policies linked" />
            ) : (
              <ul className="divide-y">
                {ctl.linked_policies.map((p: any) => (
                  <li key={p.id} className="flex items-center gap-3 px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <Link
                        to={`/policies/${p.id}`}
                        className="mono text-ink-faint hover:text-accent"
                      >
                        {p.reference}
                      </Link>
                      <p className="truncate text-sm text-ink">{p.title}</p>
                    </div>
                    {p.realignment_required ? (
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() =>
                          run(
                            'align',
                            () => api.post(`/controls/${id}/confirm-alignment/${p.id}`),
                            'Alignment confirmed',
                          )
                        }
                      >
                        <ShieldCheck className="h-3.5 w-3.5" />
                        Confirm by {formatDate(p.realignment_due)}
                      </button>
                    ) : (
                      <span className="chip border-line bg-surface-sunken text-ink-faint">
                        aligned
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'invariants' && (
        <Card title="Invariants on this control">
          <InvariantList invariants={ctl.invariants} />
        </Card>
      )}

      {/* deployment drawer */}
      <Modal
        open={!!deployment}
        onClose={() => setDeployment(null)}
        wide
        title={deployment ? `${deployment.reference} — ${deployment.asset_name}` : ''}
        description="Control effectiveness is assessed here, per deployment. Only Active and Degraded deployments are assessable (DL-2)."
      >
        {deployment && (
          <DeploymentPanel
            deployment={deployment}
            refData={ref}
            busy={busy}
            onAssess={(body) =>
              run(
                'ce',
                () => api.post(`/controls/deployments/${deployment.id}/ce`, body),
                'Control effectiveness recorded',
              )
            }
            onTest={(body) =>
              run(
                'test',
                () => api.post(`/controls/deployments/${deployment.id}/tests`, body),
                body.result === 'Fail'
                  ? 'Failing test recorded'
                  : 'Test result recorded',
                body.result === 'Fail'
                  ? 'The deployment moved to Failed. Check the parent control and every linked risk and threat model.'
                  : undefined,
              )
            }
            onTransition={async (target, reason) => {
              setBusy(target)
              try {
                const res = await api.post<any>(
                  `/controls/deployments/${deployment.id}/transition`,
                  { target, reason },
                )
                setDeployment(res.deployment)
                await load()
                const effects: any[] = res.transition.cascades ?? []
                push({
                  kind: effects.length ? 'info' : 'ok',
                  title: `Deployment moved to ${label(target)}`,
                  body: effects.length
                    ? effects.map((e) => e.description).join('; ')
                    : undefined,
                })
              } catch (err) {
                fail(err, 'Transition blocked')
              } finally {
                setBusy(null)
              }
            }}
          />
        )}
      </Modal>

      {/* create activity */}
      <Modal
        open={modal?.type === 'activity'}
        onClose={() => setModal(null)}
        title="New control activity"
        description="How the objective is implemented. Activities start as Draft and cannot be linked to risk records until Active (AL-2)."
      >
        <SimpleForm
          fields={[
            { key: 'title', label: 'Title', required: true },
            { key: 'description', label: 'Description', type: 'textarea' },
            {
              key: 'control_operator_id',
              label: 'Control operator',
              type: 'select',
              options: [{ value: '', text: 'Unassigned' }].concat(
                users.map((u) => ({ value: u.id, text: u.full_name })),
              ),
            },
          ]}
          submitLabel="Create activity"
          onSubmit={async (values) => {
            const ok = await run(
              'activity',
              () => api.post('/controls/activities', { ...values, objective_id: id }),
              'Activity created',
            )
            if (ok) setModal(null)
          }}
        />
      </Modal>

      {/* create deployment */}
      <Modal
        open={modal?.type === 'deployment'}
        onClose={() => setModal(null)}
        title="Deploy to an asset"
        description="Deployments start as Planned. A planned control does not reduce residual risk (RINV-9)."
      >
        <SimpleForm
          fields={[
            {
              key: 'attack_surface_id',
              label: 'Asset',
              type: 'select',
              required: true,
              options: assets.map((a) => ({ value: a.id, text: `${a.name} (${label(a.tier)})` })),
            },
            {
              key: 'test_frequency',
              label: 'Test frequency',
              type: 'select',
              options: (ref?.test_frequencies ?? ['Quarterly']).map((f: string) => ({
                value: f,
                text: `${f} — evidence expires after ${ref?.ce_expiry_months?.[f] ?? '?'} months`,
              })),
            },
          ]}
          submitLabel="Create deployment"
          onSubmit={async (values) => {
            const ok = await run(
              'deployment',
              () =>
                api.post('/controls/deployments', {
                  ...values,
                  activity_id: modal.activity.id,
                }),
              'Deployment created',
            )
            if (ok) setModal(null)
          }}
        />
      </Modal>

      {/* activity transition */}
      <Modal
        open={modal?.type === 'activity-transition'}
        onClose={() => setModal(null)}
        title={modal?.activity ? `${modal.activity.reference} lifecycle` : ''}
        description="AL-1: an activity cannot retire while it still has live deployments."
      >
        {modal?.activity && (
          <ActivityGates
            activityId={modal.activity.id}
            onFire={async (target, reason) => {
              const ok = await run(
                'act-' + target,
                () =>
                  api.post(`/controls/activities/${modal.activity.id}/transition`, {
                    target,
                    reason,
                  }),
                `Activity moved to ${label(target)}`,
              )
              if (ok) setModal(null)
            }}
            busy={busy}
          />
        )}
      </Modal>
    </>
  )
}

function DeploymentPanel({
  deployment,
  refData,
  busy,
  onAssess,
  onTest,
  onTransition,
}: {
  deployment: any
  refData: any
  busy: string | null
  onAssess: (body: any) => void
  onTest: (body: any) => void
  onTransition: (target: string, reason?: string) => void
}) {
  const [ce, setCe] = useState(deployment.ce_rating)
  const [evidence, setEvidence] = useState(deployment.ce_evidence_ref ?? '')
  const [notes, setNotes] = useState(deployment.ce_notes ?? '')
  const [testResult, setTestResult] = useState('Pass')
  const [testEvidence, setTestEvidence] = useState('')
  const [testNotes, setTestNotes] = useState('')

  useEffect(() => {
    setCe(deployment.ce_rating)
    setEvidence(deployment.ce_evidence_ref ?? '')
    setNotes(deployment.ce_notes ?? '')
  }, [deployment])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge value={deployment.deployment_status} />
        <Badge value={deployment.ce_rating} />
        {deployment.ce_expired && deployment.ce_rating !== 'CE-Unvalidated' && (
          <span className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300">
            evidence expired
          </span>
        )}
        <span className="ml-auto text-xs text-ink-muted">
          assessed {formatDate(deployment.ce_assessed_at)} · next test due{' '}
          {formatDate(deployment.next_test_due)}
        </span>
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-ink">Control effectiveness</h3>
        {!deployment.ce_editable ? (
          <p className="rounded-lg border bg-surface-sunken px-3 py-2.5 text-sm text-ink-muted">
            This deployment is {label(deployment.deployment_status)}, so effectiveness is not
            assessable (DL-2
            {deployment.deployment_status === 'Decommissioned' ? ' / CINV-4' : ''}).
          </p>
        ) : (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Rating">
                <select className="field" value={ce} onChange={(e) => setCe(e.target.value)}>
                  {(refData?.ce_ratings ?? []).map((r: string) => (
                    <option key={r} value={r}>
                      {r} — reduces likelihood by up to{' '}
                      {refData?.ce_likelihood_reduction?.[r] ?? 0}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Notes">
                <input className="field" value={notes} onChange={(e) => setNotes(e.target.value)} />
              </Field>
            </div>
            <Field
              label="Evidence reference"
              hint="CINV-1: anything above CE-Unvalidated requires evidence. Verbal attestation is not evidence."
            >
              <textarea
                className="field"
                rows={2}
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
                placeholder="Configurations, logs, dashboards, audit artefacts, test output"
              />
            </Field>
            <button
              className="btn-primary"
              disabled={busy === 'ce'}
              onClick={() =>
                onAssess({ ce_rating: ce, ce_evidence_ref: evidence, ce_notes: notes })
              }
            >
              Record assessment
            </button>
          </div>
        )}
      </section>

      <section className="border-t pt-4">
        <h3 className="mb-2 text-sm font-semibold text-ink">Record a control test</h3>
        <p className="mb-3 text-xs text-ink-muted">
          Test history is immutable: the database rejects UPDATE and DELETE (CINV-7). A failing
          test moves the deployment through its state machine and propagates to the parent
          objective (DL-1).
        </p>
        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-3">
            {['Pass', 'Partial', 'Fail'].map((r) => (
              <button
                key={r}
                onClick={() => setTestResult(r)}
                className={cx(
                  'rounded-lg border px-3 py-2 text-sm font-medium',
                  testResult === r
                    ? r === 'Fail'
                      ? 'border-rose-400 bg-rose-500 text-white'
                      : r === 'Partial'
                        ? 'border-amber-400 bg-amber-500 text-white'
                        : 'border-emerald-400 bg-emerald-500 text-white'
                    : 'bg-surface-sunken text-ink-muted hover:text-ink',
                )}
              >
                {r}
              </button>
            ))}
          </div>
          <Field label="Evidence reference">
            <input
              className="field"
              value={testEvidence}
              onChange={(e) => setTestEvidence(e.target.value)}
            />
          </Field>
          <Field label="Notes">
            <textarea
              className="field"
              rows={2}
              value={testNotes}
              onChange={(e) => setTestNotes(e.target.value)}
            />
          </Field>
          <button
            className={testResult === 'Fail' ? 'btn-danger' : 'btn-primary'}
            disabled={busy === 'test'}
            onClick={() => {
              onTest({ result: testResult, evidence_ref: testEvidence, notes: testNotes })
              setTestEvidence('')
              setTestNotes('')
            }}
          >
            <FlaskConical className="h-4 w-4" />
            Record {testResult.toLowerCase()}
          </button>
        </div>
      </section>

      <section className="border-t pt-4">
        <h3 className="mb-2 text-sm font-semibold text-ink">Lifecycle</h3>
        <GatePanel
          gates={deployment.gates}
          onFire={onTransition}
          busy={busy}
          reasonPrompt={(t) => t === 'Decommissioned'}
        />
      </section>

      {deployment.tests.length > 0 && (
        <section className="border-t pt-4">
          <h3 className="mb-2 text-sm font-semibold text-ink">
            Test history ({deployment.tests.length})
          </h3>
          <ul className="divide-y">
            {deployment.tests.map((t: any) => (
              <li key={t.id} className="flex gap-3 py-2.5">
                <Badge value={t.result} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">{t.evidence_ref ?? 'No evidence reference'}</p>
                  {t.notes && <p className="mt-0.5 text-xs text-ink-muted">{t.notes}</p>}
                </div>
                <span className="shrink-0 text-xs text-ink-faint">
                  #{t.sequence} · {formatDateTime(t.tested_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function ActivityGates({
  activityId,
  onFire,
  busy,
}: {
  activityId: string
  onFire: (target: string, reason?: string) => void
  busy: string | null
}) {
  const [gates, setGates] = useState<any[] | null>(null)
  useEffect(() => {
    api
      .get<any[]>(`/controls/activities/${activityId}/gates`)
      .then(setGates)
      .catch(() => setGates([]))
  }, [activityId])
  if (!gates) return <PageLoader />
  return <GatePanel gates={gates as any} onFire={onFire} busy={busy?.replace('act-', '')} />
}

function SimpleForm({
  fields,
  submitLabel,
  onSubmit,
}: {
  fields: {
    key: string
    label: string
    type?: string
    required?: boolean
    options?: { value: string; text: string }[]
  }[]
  submitLabel: string
  onSubmit: (values: Record<string, string>) => void
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, f.options?.[0]?.value ?? ''])),
  )
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '')))
      }}
    >
      {fields.map((f) => (
        <Field key={f.key} label={f.label}>
          {f.type === 'textarea' ? (
            <textarea
              className="field"
              rows={3}
              value={values[f.key] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          ) : f.type === 'select' ? (
            <select
              className="field"
              value={values[f.key] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            >
              {(f.options ?? []).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.text}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="field"
              value={values[f.key] ?? ''}
              required={f.required}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          )}
        </Field>
      ))}
      <div className="flex justify-end border-t pt-4">
        <button className="btn-primary">{submitLabel}</button>
      </div>
    </form>
  )
}
