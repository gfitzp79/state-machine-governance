import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, ShieldCheck } from 'lucide-react'
import { api, ApiError, getStoredUser } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Badge, Card, Detail, Empty, Field, PageLoader, useToast } from '../components/ui'
import { GatePanel } from '../components/governance'
import { cx, formatDate, formatDateTime, label } from '../lib/format'

export default function TreatmentDetail() {
  const { id = '' } = useParams()
  const me = getStoredUser()
  const [t, setT] = useState<any>(null)
  const [users, setUsers] = useState<any[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const { push } = useToast()

  const load = useCallback(() => api.get<any>(`/treatments/${id}`).then(setT), [id])

  useEffect(() => {
    load().catch(() => undefined)
    api.get<any[]>('/users').then(setUsers).catch(() => undefined)
  }, [load])

  const fail = (err: unknown, title = 'Refused') =>
    err instanceof ApiError
      ? push({ kind: 'error', title, body: err.message, rule: err.rule })
      : push({ kind: 'error', title, body: String(err) })

  const run = async (key: string, fn: () => Promise<unknown>, okTitle: string) => {
    setBusy(key)
    try {
      await fn()
      await load()
      push({ kind: 'ok', title: okTitle })
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
      const res = await api.post<any>(`/treatments/${id}/transition`, { target, reason })
      setT(res.treatment)
      const effects: any[] = res.transition.cascades ?? []
      push({
        kind: effects.length ? 'info' : 'ok',
        title: `Treatment moved to ${label(target)}`,
        body: effects.length ? effects.map((e) => e.description).join('; ') : undefined,
      })
    } catch (err) {
      fail(err, 'Transition blocked')
    } finally {
      setBusy(null)
    }
  }

  if (!t) return <PageLoader />

  const userName = (uid: string | null) => users.find((u) => u.id === uid)?.full_name ?? '—'
  const isOwner = me?.id === t.treatment_owner_id

  return (
    <>
      <Link
        to="/treatments"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" />
        Treatments
      </Link>

      <PageHeader
        eyebrow={t.reference}
        title={t.title}
        description={t.description}
        meta={
          <>
            <Badge value={t.lifecycle_state} />
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              {t.treatment_type}
            </span>
            {t.overdue && (
              <span className="chip border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300">
                Overdue
              </span>
            )}
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="RINV-12: the two confirmations"
          subtitle="A treatment cannot be presented at readout without both. They must come from different people (SEP-5)."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div
              className={cx(
                'rounded-lg border p-4',
                t.grc_eng_validated
                  ? 'border-emerald-300 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20'
                  : 'bg-surface-sunken',
              )}
            >
              <div className="flex items-center gap-2">
                <ShieldCheck
                  className={cx(
                    'h-4 w-4',
                    t.grc_eng_validated ? 'text-emerald-600' : 'text-ink-faint',
                  )}
                />
                <p className="text-sm font-semibold text-ink">GRC Engineer validation</p>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                Confirms the treatment is technically deliverable as designed, and that the
                control mapping is sound.
              </p>
              {t.grc_eng_validated ? (
                <>
                  <p className="mt-3 text-sm text-ink">
                    Validated by {userName(t.grc_eng_validated_by)}
                  </p>
                  {t.grc_eng_validation_notes && (
                    <p className="mt-1 text-xs text-ink-muted">{t.grc_eng_validation_notes}</p>
                  )}
                </>
              ) : (
                <div className="mt-3 space-y-2">
                  <input className="field" id="grc-notes" placeholder="Validation notes" />
                  <button
                    className="btn-primary btn-sm w-full"
                    disabled={busy === 'validate'}
                    onClick={() => {
                      const el = document.getElementById('grc-notes') as HTMLInputElement
                      run(
                        'validate',
                        () => api.post(`/treatments/${id}/validate`, { notes: el?.value ?? '' }),
                        'Feasibility validated',
                      )
                    }}
                  >
                    Record validation
                  </button>
                  <p className="text-xs text-ink-faint">
                    Requires the GRC_Engineer role, and you cannot validate a treatment you own.
                  </p>
                </div>
              )}
            </div>

            <div
              className={cx(
                'rounded-lg border p-4',
                t.owner_committed
                  ? 'border-emerald-300 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20'
                  : 'bg-surface-sunken',
              )}
            >
              <div className="flex items-center gap-2">
                <CheckCircle2
                  className={cx(
                    'h-4 w-4',
                    t.owner_committed ? 'text-emerald-600' : 'text-ink-faint',
                  )}
                />
                <p className="text-sm font-semibold text-ink">Treatment owner commitment</p>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                The named owner accepts accountability for delivering this by the target date.
              </p>
              {t.owner_committed ? (
                <p className="mt-3 text-sm text-ink">
                  Committed by {userName(t.treatment_owner_id)} ·{' '}
                  {formatDateTime(t.owner_committed_at)}
                </p>
              ) : (
                <div className="mt-3 space-y-2">
                  <button
                    className="btn-primary btn-sm w-full"
                    disabled={busy === 'commit' || !t.treatment_owner_id}
                    onClick={() =>
                      run('commit', () => api.post(`/treatments/${id}/commit`), 'Commitment recorded')
                    }
                  >
                    {isOwner ? 'I commit to delivering this' : 'Record commitment'}
                  </button>
                  <p className="text-xs text-ink-faint">
                    {t.treatment_owner_id
                      ? isOwner
                        ? 'You are the named owner.'
                        : `Only ${userName(t.treatment_owner_id)} can record their own commitment.`
                      : 'Assign an owner first.'}
                  </p>
                </div>
              )}
            </div>
          </div>
        </Card>

        <Card title="Lifecycle">
          <GatePanel
            gates={t.gates}
            onFire={transition}
            busy={busy}
            reasonPrompt={(x) => x === 'Cancelled'}
          />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Plan" className="lg:col-span-1">
          <dl className="divide-y">
            <Detail label="Owner">
              <select
                className="field"
                value={t.treatment_owner_id ?? ''}
                onChange={(e) =>
                  run(
                    'patch',
                    () =>
                      api.patch(`/treatments/${id}`, {
                        treatment_owner_id: e.target.value || null,
                      }),
                    'Owner updated',
                  )
                }
              >
                <option value="">Unassigned</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </select>
            </Detail>
            <Detail label="Target date">
              <input
                className="field"
                type="date"
                defaultValue={t.target_date ?? ''}
                onChange={(e) =>
                  run(
                    'patch',
                    () => api.patch(`/treatments/${id}`, { target_date: e.target.value }),
                    'Target date updated',
                  )
                }
              />
            </Detail>
            <Detail label="Expected reduction">
              impact {t.expected_impact_delta}, likelihood {t.expected_likelihood_delta}
            </Detail>
            <Detail label="Effort">
              {t.loe ?? '—'}
              {t.loe_implementation_hours ? ` · ${t.loe_implementation_hours}h build` : ''}
              {t.loe_operational_hours_pa ? ` · ${t.loe_operational_hours_pa}h/yr run` : ''}
            </Detail>
            <Detail label="Evidence reference">
              <textarea
                className="field"
                rows={3}
                defaultValue={t.evidence_ref ?? ''}
                placeholder="Required to mark the treatment Complete"
                onBlur={(e) =>
                  e.target.value !== (t.evidence_ref ?? '') &&
                  run(
                    'patch',
                    () => api.patch(`/treatments/${id}`, { evidence_ref: e.target.value }),
                    'Evidence saved',
                  )
                }
              />
            </Detail>
          </dl>
        </Card>

        <Card
          className="lg:col-span-2"
          title="Progress check-ins"
          subtitle="Append-only. The drift trail for residual gate condition 5 is built from these."
        >
          <CheckinForm
            onSubmit={(body) =>
              run('checkin', () => api.post(`/treatments/${id}/checkins`, body), 'Check-in recorded')
            }
          />
          {t.checkins.length === 0 ? (
            <Empty
              title="No check-ins yet"
              hint="A treatment cannot be marked Complete without at least one."
            />
          ) : (
            <ul className="mt-4 divide-y">
              {t.checkins.map((c: any) => (
                <li key={c.id} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge value={c.status} />
                    <span className="text-sm text-ink">{userName(c.submitted_by)}</span>
                    <span className="ml-auto text-xs text-ink-faint">
                      {formatDateTime(c.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted">{c.notes}</p>
                  {c.blockers && (
                    <p className="mt-1 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                      Blocker: {c.blockers}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Approvals" bodyClassName={t.approvals.length ? 'p-0' : undefined}>
          {t.approvals.length === 0 ? (
            <div className="space-y-3">
              <p className="text-sm text-ink-muted">
                No approval requested. A treatment cannot reach Approved without one.
              </p>
              <button
                className="btn-ghost"
                disabled={busy === 'approval'}
                onClick={() =>
                  run(
                    'approval',
                    () => api.post(`/treatments/${id}/approvals`, {}),
                    'Approval requested',
                  )
                }
              >
                Request approval
              </button>
            </div>
          ) : (
            <ul className="divide-y">
              {t.approvals.map((a: any) => (
                <li key={a.id} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-ink">{label(a.approval_type)}</span>
                    <Badge value={a.decision} />
                    <span className="ml-auto text-xs text-ink-faint">
                      requested by {userName(a.requested_by)}
                    </span>
                  </div>
                  {a.decision === 'Pending' ? (
                    <div className="mt-2 flex gap-2">
                      <button
                        className="btn-primary btn-sm"
                        onClick={() =>
                          run(
                            'decide',
                            () =>
                              api.post(`/treatments/${id}/approvals/${a.id}/decide`, {
                                decision: 'Approved',
                              }),
                            'Approved',
                          )
                        }
                      >
                        Approve
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() =>
                          run(
                            'decide',
                            () =>
                              api.post(`/treatments/${id}/approvals/${a.id}/decide`, {
                                decision: 'Rejected',
                              }),
                            'Rejected',
                          )
                        }
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <p className="mt-1 text-xs text-ink-muted">
                      {userName(a.decision_by)} · {formatDateTime(a.decision_at)}
                      {a.decision_notes ? ` — ${a.decision_notes}` : ''}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Linked risks"
          subtitle="Completing this treatment satisfies residual gate condition 1 on each, once every treatment on that risk is complete."
          bodyClassName={t.linked_risks.length ? 'p-0' : undefined}
        >
          {t.linked_risks.length === 0 ? (
            <Empty title="Not linked to any risk" />
          ) : (
            <ul className="divide-y">
              {t.linked_risks.map((r: any) => (
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
      </div>
    </>
  )
}

function CheckinForm({ onSubmit }: { onSubmit: (b: any) => Promise<boolean> }) {
  const [status, setStatus] = useState('On_Track')
  const [notes, setNotes] = useState('')
  const [blockers, setBlockers] = useState('')

  return (
    <div className="space-y-3 rounded-lg border bg-surface-sunken p-3">
      <div className="grid gap-2 sm:grid-cols-4">
        {['On_Track', 'At_Risk', 'Blocked', 'Delivered'].map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={cx(
              'rounded-lg border px-2 py-1.5 text-xs font-medium',
              status === s
                ? 'border-accent bg-accent text-white'
                : 'bg-surface-raised text-ink-muted hover:text-ink',
            )}
          >
            {label(s)}
          </button>
        ))}
      </div>
      <Field label="Notes">
        <textarea
          className="field"
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </Field>
      {(status === 'At_Risk' || status === 'Blocked') && (
        <Field label="Blockers">
          <input
            className="field"
            value={blockers}
            onChange={(e) => setBlockers(e.target.value)}
          />
        </Field>
      )}
      <button
        className="btn-primary btn-sm"
        disabled={!notes.trim()}
        onClick={async () => {
          if (await onSubmit({ status, notes, blockers: blockers || null })) {
            setNotes('')
            setBlockers('')
          }
        }}
      >
        Record check-in
      </button>
    </div>
  )
}
