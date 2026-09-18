import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, Link2, Plus, X } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
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
import { GatePanel, InvariantList } from '../components/governance'
import { cx, formatDate, formatDateTime, label, relativeDays } from '../lib/format'

export default function PolicyDetail() {
  const { id = '' } = useParams()
  const [policy, setPolicy] = useState<any>(null)
  const [controls, setControls] = useState<any[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [tab, setTab] = useState('lifecycle')
  const [busy, setBusy] = useState<string | null>(null)
  const [modal, setModal] = useState<string | null>(null)
  const { push } = useToast()

  const load = useCallback(() => api.get<any>(`/policies/${id}`).then(setPolicy), [id])

  useEffect(() => {
    load().catch(() => undefined)
    api.get<any[]>('/controls').then(setControls).catch(() => undefined)
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
      const res = await api.post<any>(`/policies/${id}/transition`, { target, reason })
      setPolicy(res.policy)
      const effects: any[] = res.transition.cascades ?? []
      push({
        kind: effects.length ? 'info' : 'ok',
        title: `Policy moved to ${label(target)}`,
        body: effects.length ? effects.map((e) => e.description).join('; ') : undefined,
      })
    } catch (err) {
      fail(err, 'Transition blocked')
    } finally {
      setBusy(null)
    }
  }

  if (!policy) return <PageLoader />

  const userName = (uid: string | null) => users.find((u) => u.id === uid)?.full_name ?? '—'

  return (
    <>
      <Link
        to="/policies"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" />
        Policies
      </Link>

      <PageHeader
        eyebrow={policy.reference}
        title={policy.title}
        description={policy.purpose}
        meta={
          <>
            <Badge value={policy.lifecycle_state} />
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              v{policy.version}
            </span>
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              {policy.review_cycle} review
            </span>
            {(policy.compliance_mappings ?? []).map((m: string) => (
              <span key={m} className="chip border-line bg-surface-sunken text-ink-faint">
                {m}
              </span>
            ))}
          </>
        }
      />

      {policy.realignment_pending > 0 && (
        <div className="mb-5 flex gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/40">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
              {policy.realignment_pending} linked control
              {policy.realignment_pending === 1 ? '' : 's'} awaiting alignment confirmation
            </p>
            <p className="mt-0.5 text-sm text-amber-800 dark:text-amber-300">
              Due {formatDate(policy.realignment_due)} ({relativeDays(policy.realignment_due)}).
              Unconfirmed alignments are flagged as governance gaps (PINV-7).
            </p>
          </div>
        </div>
      )}

      <div className="mb-5">
        <Tabs
          tabs={[
            { id: 'lifecycle', label: 'Lifecycle' },
            { id: 'content', label: 'Content' },
            { id: 'controls', label: 'Linked controls', count: policy.controls.length },
            { id: 'exceptions', label: 'Exceptions', count: policy.exceptions.length },
            { id: 'versions', label: 'Version history', count: policy.versions.length },
            { id: 'invariants', label: 'Invariants', count: policy.invariants.length },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'lifecycle' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Available transitions"
            subtitle="A revision keeps the Active version enforceable throughout (PL-3). Deprecation is blocked while a linked risk is Critical or High and unmitigated (PINV-8)."
          >
            <GatePanel
              gates={policy.gates}
              onFire={transition}
              busy={busy}
              reasonPrompt={(t) => t === 'Under_Revision'}
            />
          </Card>

          <Card title="Approval and dates">
            <dl className="divide-y">
              <Detail label="Approved by">
                {policy.approved_by ? (
                  <>
                    {userName(policy.approved_by)} · {formatDateTime(policy.approved_at)}
                  </>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-ink-muted">
                      PINV-5: approval requires CISO or above, and never the policy owner.
                    </p>
                    <div className="flex gap-2">
                      <select className="field" id="approver">
                        <option value="">Select approver</option>
                        {users.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.full_name} — {u.seniority}
                          </option>
                        ))}
                      </select>
                      <button
                        className="btn-primary shrink-0"
                        disabled={busy === 'approve'}
                        onClick={() => {
                          const el = document.getElementById('approver') as HTMLSelectElement
                          if (!el?.value) return
                          run(
                            'approve',
                            () => api.post(`/policies/${id}/approve`, { approver_id: el.value }),
                            'Policy approved',
                          )
                        }}
                      >
                        Approve
                      </button>
                    </div>
                  </div>
                )}
              </Detail>
              <Detail label="Policy owner">
                <select
                  className="field"
                  value={policy.policy_owner_id ?? ''}
                  onChange={(e) =>
                    run(
                      'patch',
                      () =>
                        api.patch(`/policies/${id}`, { policy_owner_id: e.target.value || null }),
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
              <Detail label="Effective date">
                <input
                  className="field"
                  type="date"
                  defaultValue={policy.effective_date ?? ''}
                  onChange={(e) =>
                    run(
                      'patch',
                      () => api.patch(`/policies/${id}`, { effective_date: e.target.value }),
                      'Effective date set',
                    )
                  }
                />
              </Detail>
              <Detail label="Next review">{formatDate(policy.next_review_date)}</Detail>
            </dl>
          </Card>
        </div>
      )}

      {tab === 'content' && (
        <Card
          title="Policy content"
          subtitle="Editing the body of an Active policy captures an immutable version first (PINV-9)."
        >
          <div className="space-y-4">
            <Field label="Scope">
              <input
                className="field"
                defaultValue={policy.scope ?? ''}
                onBlur={(e) =>
                  e.target.value !== (policy.scope ?? '') &&
                  run('patch', () => api.patch(`/policies/${id}`, { scope: e.target.value }), 'Saved')
                }
              />
            </Field>
            <Field label="Purpose">
              <input
                className="field"
                defaultValue={policy.purpose ?? ''}
                onBlur={(e) =>
                  e.target.value !== (policy.purpose ?? '') &&
                  run('patch', () => api.patch(`/policies/${id}`, { purpose: e.target.value }), 'Saved')
                }
              />
            </Field>
            <Field label="Change summary" hint="Required to approve a revision (PL-4).">
              <input
                className="field"
                defaultValue={policy.change_summary ?? ''}
                onBlur={(e) =>
                  e.target.value !== (policy.change_summary ?? '') &&
                  run(
                    'patch',
                    () => api.patch(`/policies/${id}`, { change_summary: e.target.value }),
                    'Saved',
                  )
                }
              />
            </Field>
            <Field label="Body">
              <textarea
                className="field font-[inherit]"
                rows={14}
                defaultValue={policy.body ?? ''}
                onBlur={(e) =>
                  e.target.value !== (policy.body ?? '') &&
                  run(
                    'patch',
                    () =>
                      api.patch(`/policies/${id}`, {
                        body: e.target.value,
                        change_summary: policy.change_summary,
                      }),
                    'Body saved; prior version captured',
                  )
                }
              />
            </Field>
          </div>
        </Card>
      )}

      {tab === 'controls' && (
        <Card
          title="Linked control objectives"
          subtitle="PINV-1: an Active policy must retain at least one. Removing the last one is refused."
          action={
            <button className="btn-ghost btn-sm" onClick={() => setModal('control')}>
              <Plus className="h-3.5 w-3.5" />
              Link control
            </button>
          }
          bodyClassName={policy.controls.length ? 'p-0' : undefined}
        >
          {policy.controls.length === 0 ? (
            <Empty
              title="No controls linked"
              hint="This policy cannot be activated until at least one control objective enforces it."
            />
          ) : (
            <ul className="divide-y">
              {policy.controls.map((c: any) => (
                <li key={c.link_id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/controls/${c.objective_id}`}
                      className="mono text-ink-faint hover:text-accent"
                    >
                      {c.reference}
                    </Link>
                    <p className="truncate text-sm text-ink">{c.title}</p>
                  </div>
                  <Badge value={c.lifecycle_state} />
                  {c.realignment_required && (
                    <span className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300">
                      re-align by {formatDate(c.realignment_due)}
                    </span>
                  )}
                  <button
                    className="text-ink-faint hover:text-rose-500"
                    onClick={() =>
                      run(
                        'unlink',
                        () => api.del(`/policies/${id}/controls/${c.link_id}`),
                        'Control unlinked',
                      )
                    }
                    aria-label="Unlink"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'exceptions' && (
        <Card
          title="Exceptions"
          subtitle="More than five active exceptions on one policy is an unscheduled review trigger."
          bodyClassName={policy.exceptions.length ? 'p-0' : undefined}
        >
          {policy.exceptions.length === 0 ? (
            <Empty title="No exceptions on this policy" />
          ) : (
            <ul className="divide-y">
              {policy.exceptions.map((e: any) => (
                <li key={e.id} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="mono text-ink-faint">{e.reference}</span>
                    <span className="font-medium text-ink">{e.title}</span>
                    <Badge value={e.lifecycle_state} />
                    <span
                      className={cx(
                        'ml-auto text-xs',
                        e.overdue
                          ? 'text-rose-600 dark:text-rose-400'
                          : e.expiring_soon
                            ? 'text-amber-600 dark:text-amber-400'
                            : 'text-ink-faint',
                      )}
                    >
                      expires {formatDate(e.expiry_date)} ({relativeDays(e.expiry_date)})
                    </span>
                  </div>
                  <ExceptionActions
                    exceptionId={e.id}
                    state={e.lifecycle_state}
                    onDone={load}
                    onError={fail}
                  />
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'versions' && (
        <Card
          title="Version history"
          subtitle="Immutable. The database rejects UPDATE and DELETE on this table (PINV-9)."
          bodyClassName="p-0"
        >
          <ul className="divide-y">
            {policy.versions.map((v: any) => (
              <li key={v.id} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="mono rounded bg-surface-sunken px-1.5 py-0.5 text-ink">
                    v{v.version}
                  </span>
                  <Badge value={v.lifecycle_state_at_capture} />
                  <span className="ml-auto text-xs text-ink-muted">
                    {userName(v.edited_by)} · {formatDateTime(v.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-ink-muted">{v.change_summary}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {tab === 'invariants' && (
        <Card title="Invariants on this policy">
          <InvariantList invariants={policy.invariants} />
        </Card>
      )}

      <Modal
        open={modal === 'control'}
        onClose={() => setModal(null)}
        title="Link a control objective"
        description="The control that enforces this policy's requirements."
      >
        <ul className="max-h-96 space-y-1 overflow-y-auto">
          {controls
            .filter((c) => !policy.controls.some((pc: any) => pc.objective_id === c.id))
            .map((c) => (
              <li key={c.id}>
                <button
                  className="flex w-full items-center gap-2 rounded-lg border bg-surface-sunken px-3 py-2.5 text-left hover:border-accent"
                  onClick={async () => {
                    const ok = await run(
                      'link',
                      () => api.post(`/policies/${id}/controls`, { id: c.id }),
                      'Control linked',
                    )
                    if (ok) setModal(null)
                  }}
                >
                  <Link2 className="h-4 w-4 shrink-0 text-ink-faint" />
                  <div className="min-w-0">
                    <p className="truncate text-sm text-ink">
                      {c.reference} — {c.title}
                    </p>
                    <p className="text-xs text-ink-muted">
                      {label(c.lifecycle_state)} · {c.effective_ce}
                    </p>
                  </div>
                </button>
              </li>
            ))}
        </ul>
      </Modal>
    </>
  )
}

function ExceptionActions({
  exceptionId,
  state,
  onDone,
  onError,
}: {
  exceptionId: string
  state: string
  onDone: () => Promise<unknown>
  onError: (e: unknown) => void
}) {
  const [gates, setGates] = useState<any[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<any>(`/exceptions/${exceptionId}`)
      .then((e) => setGates(e.gates))
      .catch(() => setGates([]))
  }, [exceptionId, state])

  if (!gates || gates.length === 0) return null

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {gates.map((g: any) => (
        <button
          key={g.target}
          className="btn-ghost btn-sm"
          disabled={!g.passed || !g.role_permitted || busy === g.target}
          title={
            g.passed
              ? g.role_permitted
                ? g.description
                : `Requires: ${g.roles.join(', ')}`
              : g.checks
                  .filter((c: any) => !c.passed)
                  .map((c: any) => `${c.id}: ${c.detail}`)
                  .join('\n')
          }
          onClick={async () => {
            setBusy(g.target)
            try {
              await api.post(`/exceptions/${exceptionId}/transition`, { target: g.target })
              await onDone()
            } catch (err) {
              onError(err)
            } finally {
              setBusy(null)
            }
          }}
        >
          {label(g.target)}
          {!g.passed && ` (${g.checks.filter((c: any) => !c.passed).length} blocking)`}
        </button>
      ))}
    </div>
  )
}
