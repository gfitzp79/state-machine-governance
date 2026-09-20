import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, Link2, Lock, Plus, Send, Unlock, X } from 'lucide-react'
import { api, ApiError, getStoredUser } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { PersonSelect } from '../components/people'
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
import {
  CEResolution,
  ConditionList,
  GatePanel,
  InvariantList,
  LifecycleRail,
  LockState,
} from '../components/governance'
import { cx, formatDate, formatDateTime, label } from '../lib/format'

const PHASES = [
  'Intake',
  'Preconditions',
  'Scoring',
  'Treatment',
  'Readout',
  'Evidence_Residual',
  'Monitoring',
]

const PRECONDITION_HELP: Record<string, string> = {
  true_risk_confirmed:
    'Triage confirms this is a risk requiring business accountability, not an issue or an out-of-scope item.',
  tier_assigned:
    'A NIST RMF tier is set and the rationale below records why that tier is the right scope for the impact assessment.',
  stakeholders_identified:
    'Risk Owner, Risk Stakeholder and Risk Analyst are all named below, and the owner and stakeholder are different people (SEP-1).',
  control_effectiveness_assessed:
    'A linked control is Operating and carries a rating above CE-Unvalidated with an evidence reference. A control the scoring engine would exclude is not an assessment.',
}

const RESIDUAL_HELP: Record<string, string> = {
  mitigations_implemented:
    'Every linked treatment is Complete. Planned mitigations do not reduce residual risk (RINV-9).',
  evidence_provided:
    'Configs, logs, dashboards or audit artefacts are attached and referenced. Verbal attestation is not evidence.',
  effectiveness_confirmed:
    'The Risk Analyst has independently reviewed the evidence. Self-assessment by the treatment owner does not satisfy this.',
  governance_approved: 'An approval record exists with an approver identity and timestamp.',
  drift_tracked:
    'The drift log shows the inherent-versus-residual delta across the treatment period, so degradation during treatment is visible.',
}

export default function RiskDetail() {
  const { id = '' } = useParams()
  const [risk, setRisk] = useState<any>(null)
  const [tab, setTab] = useState('lifecycle')
  const [busy, setBusy] = useState<string | null>(null)
  const [users, setUsers] = useState<any[]>([])
  const [assets, setAssets] = useState<any[]>([])
  const [controls, setControls] = useState<any[]>([])
  const [treatments, setTreatments] = useState<any[]>([])
  const [modal, setModal] = useState<string | null>(null)
  const { push } = useToast()

  const load = useCallback(() => api.get<any>(`/risks/${id}`).then(setRisk), [id])

  useEffect(() => {
    load().catch(() => undefined)
    api.get<any[]>('/users').then(setUsers).catch(() => undefined)
    api.get<any[]>('/assets').then(setAssets).catch(() => undefined)
    api.get<any[]>('/controls').then(setControls).catch(() => undefined)
    api.get<any[]>('/treatments').then(setTreatments).catch(() => undefined)
  }, [load])

  const fail = (err: unknown, title: string) => {
    if (err instanceof ApiError) {
      push({ kind: 'error', title, body: err.message, rule: err.rule })
    } else {
      push({ kind: 'error', title, body: String(err) })
    }
  }

  const run = async (key: string, fn: () => Promise<unknown>, okTitle: string, okBody?: string) => {
    setBusy(key)
    try {
      await fn()
      await load()
      push({ kind: 'ok', title: okTitle, body: okBody })
      return true
    } catch (err) {
      fail(err, 'Refused')
      return false
    } finally {
      setBusy(null)
    }
  }

  const transition = async (target: string, reason?: string) => {
    setBusy(target)
    try {
      const res = await api.post<any>(`/risks/${id}/transition`, { target, reason })
      setRisk(res.risk)
      const effects: any[] = res.transition.cascades ?? []
      push({
        kind: 'ok',
        title: `Advanced to ${label(target)}`,
        body: effects.length
          ? `${effects.length} cascade effect${effects.length === 1 ? '' : 's'}: ${effects
              .map((e) => e.description)
              .join('; ')}`
          : undefined,
      })
    } catch (err) {
      fail(err, 'Transition blocked')
    } finally {
      setBusy(null)
    }
  }

  const patch = (body: Record<string, unknown>, title: string) =>
    run('patch', () => api.patch(`/risks/${id}`, body), title)

  if (!risk) return <PageLoader />

  const userName = (uid: string | null) =>
    users.find((u) => u.id === uid)?.full_name ?? (uid ? 'Unknown user' : '—')

  const tabs = [
    { id: 'lifecycle', label: 'Lifecycle' },
    { id: 'scoring', label: 'Scoring' },
    { id: 'treatment', label: 'Treatment' },
    { id: 'links', label: 'Links', count: risk.controls.length + risk.treatments.length },
    { id: 'invariants', label: 'Invariants', count: risk.invariants.length },
    { id: 'history', label: 'History', count: risk.history.length },
    { id: 'discussion', label: 'Discussion', count: risk.comments.length },
  ]

  return (
    <>
      <Link
        to="/risks"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" />
        Risk register
      </Link>

      <PageHeader
        eyebrow={risk.reference}
        title={risk.title}
        description={risk.statement ?? 'The structured risk statement is incomplete.'}
        meta={
          <>
            <Badge value={risk.lifecycle_state} />
            {risk.tier && (
              <span className="chip border-line bg-surface-sunken text-ink-faint">
                {label(risk.tier)}
              </span>
            )}
            <Badge value={risk.inherent_rating}>
              Inherent {risk.inherent_risk_score ?? '—'}{' '}
              {risk.inherent_rating ? `(${risk.inherent_rating})` : ''}
            </Badge>
            <LockState locked={risk.residual_score_locked}>
              {risk.residual_score_locked
                ? 'Residual locked'
                : `Residual ${risk.residual_risk_score ?? '—'} (${risk.residual_rating ?? '—'})`}
            </LockState>
            <span className="chip border-line bg-surface-sunken text-ink-muted">
              Reported {risk.reported_score ?? '—'} · {risk.appetite ?? 'not yet scored'}
            </span>
          </>
        }
      />

      {risk.control_change_flag && (
        <div className="mb-5 flex gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/40">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
              {label(risk.control_change_flag)}
            </p>
            <p className="mt-0.5 text-sm text-amber-800 dark:text-amber-300">
              {risk.control_change_detail}
            </p>
          </div>
        </div>
      )}

      {risk.escalation_flag && (
        <div className="mb-5 flex gap-3 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 dark:border-rose-900 dark:bg-rose-950/40">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
          <div>
            <p className="text-sm font-medium text-rose-900 dark:text-rose-200">Escalated</p>
            <p className="mt-0.5 text-sm text-rose-800 dark:text-rose-300">
              {risk.escalation_reason}
            </p>
          </div>
        </div>
      )}

      <Card className="mb-5" bodyClassName="px-5 py-4">
        <LifecycleRail states={PHASES} current={risk.lifecycle_state} terminal={['Closed']} />
      </Card>

      <div className="mb-5">
        <Tabs tabs={tabs} active={tab} onChange={setTab} />
      </div>

      {tab === 'lifecycle' && (
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <Card
              title="Available transitions"
              subtitle="Each precondition is evaluated live. A blocked transition names the rule blocking it."
            >
              <GatePanel
                gates={risk.gates}
                onFire={transition}
                busy={busy}
                reasonPrompt={(t) =>
                  ['Preconditions', 'Closed'].includes(t) && risk.lifecycle_state !== 'Intake'
                }
              />
            </Card>
          </div>

          <div className="space-y-4 lg:col-span-2">
            <Card
              title="Phase 2 preconditions"
              subtitle="All four must hold before scoring fields open (RINV-8)."
            >
              <ConditionList
                conditions={risk.preconditions}
                descriptions={PRECONDITION_HELP}
                disabled={risk.phase > 2}
                derived={risk.derived_preconditions ?? []}
                onToggle={(key, value) => {
                  // Only the triage judgement is writable. The rest are read
                  // from the record, so there is nothing to send.
                  if (key !== 'true_risk_confirmed') return
                  patch({ pre_true_risk_confirmed: value }, 'Triage decision recorded')
                }}
              />
            </Card>

            <Card
              title="Scope"
              subtitle="Which assets this risk concerns. A control only reduces it where it is deployed (RINV-14)."
            >
              <ScopeEditor
                scope={risk.scope_assets ?? []}
                assets={assets}
                busy={busy === 'scope'}
                onAdd={(assetId) =>
                  run('scope', () => api.post(`/risks/${id}/assets`, { id: assetId }), 'Scope updated')
                }
                onRemove={(assetId) =>
                  run('scope', () => api.del(`/risks/${id}/assets/${assetId}`), 'Scope updated')
                }
              />
            </Card>

            <Card title="Ownership" subtitle="RINV-10 and SEP-1 are enforced on these fields.">
              <div className="space-y-3">
                {[
                  [
                    'risk_owner_id',
                    'Risk Owner',
                    'Accountable for the decision and the residual.',
                    'Risk_Owner',
                  ],
                  [
                    'risk_stakeholder_id',
                    'Risk Stakeholder',
                    'Senior oversight. Must differ from the Risk Owner (SEP-1).',
                    'Risk_Stakeholder',
                  ],
                  [
                    'risk_analyst_id',
                    'Risk Analyst',
                    'Assessment, scoring and validation.',
                    'Risk_Analyst',
                  ],
                ].map(([field, text, hint, role]) => (
                  <PersonSelect
                    key={field}
                    label={text}
                    hint={hint}
                    role={role}
                    value={risk[field]}
                    onChange={(id) => patch({ [field]: id }, 'Ownership updated')}
                    exclude={field === 'risk_stakeholder_id' ? risk.risk_owner_id : undefined}
                    excludeReason="already the Risk Owner"
                  />
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}

      {tab === 'scoring' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Inherent score"
            subtitle="Exposure with no controls in place. Likelihood is scored without CE adjustment (LKH-3)."
            action={risk.inherent_locked ? <LockState locked>Frozen</LockState> : undefined}
          >
            {risk.phase < 3 ? (
              <Empty
                title="Scoring is not yet open"
                hint="The Phase 2 preconditions gate must pass before the scoring fields become editable (RINV-8)."
              />
            ) : (
              <ScoreForm
                disabled={risk.inherent_locked}
                impact={risk.impact}
                likelihood={risk.likelihood}
                impactRationale={risk.impact_justification}
                likelihoodRationale={risk.likelihood_justification}
                impactLabel="Impact justification"
                likelihoodLabel="Likelihood justification"
                busy={busy === 'inherent'}
                onSubmit={(impact, likelihood, ir, lr) =>
                  run(
                    'inherent',
                    () =>
                      api.post(`/risks/${id}/score/inherent`, {
                        impact,
                        likelihood,
                        impact_justification: ir,
                        likelihood_justification: lr,
                      }),
                    'Inherent score recorded',
                  )
                }
              />
            )}
          </Card>

          <Card
            title="Residual score"
            subtitle="Remaining exposure after validated treatment. Locked until all five gate conditions hold (RINV-1)."
            action={<LockState locked={risk.residual_score_locked} />}
          >
            {risk.residual_score_locked ? (
              <div className="space-y-4">
                <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                  Residual scoring is locked. Until the gate passes, this risk reports its
                  inherent score of <strong>{risk.inherent_risk_score ?? '—'}</strong> (RES-2).
                </p>
                <ConditionList
                  conditions={risk.residual_gate}
                  descriptions={RESIDUAL_HELP}
                  onToggle={(key, value) => {
                    const map: Record<string, string> = {
                      mitigations_implemented: 'gate_mitigations_implemented',
                      evidence_provided: 'gate_evidence_provided',
                      effectiveness_confirmed: 'gate_effectiveness_confirmed',
                      governance_approved: 'gate_governance_approved',
                      drift_tracked: 'gate_drift_tracked',
                    }
                    patch({ [map[key]]: value }, 'Gate condition updated')
                  }}
                />
                <Field
                  label="Evidence reference"
                  hint="Condition 2 needs a reference, not just a tick."
                >
                  <textarea
                    className="field"
                    rows={2}
                    defaultValue={risk.evidence_ref ?? ''}
                    onBlur={(e) =>
                      e.target.value !== (risk.evidence_ref ?? '') &&
                      patch({ evidence_ref: e.target.value }, 'Evidence reference saved')
                    }
                    placeholder="Configs, logs, dashboards, audit artefacts"
                  />
                </Field>
                <button
                  className="btn-ghost w-full"
                  disabled={
                    busy === 'unlock' || !Object.values(risk.residual_gate).every(Boolean)
                  }
                  onClick={() =>
                    run(
                      'unlock',
                      () => api.post(`/risks/${id}/residual/unlock`),
                      'Residual scoring unlocked',
                      'All five conditions of GATE_RESIDUAL_VALIDATED are satisfied.',
                    )
                  }
                >
                  <Unlock className="h-4 w-4" />
                  Release the residual lock
                </button>
              </div>
            ) : (
              <ScoreForm
                impact={risk.residual_impact}
                likelihood={risk.residual_likelihood}
                impactRationale={risk.residual_impact_rationale}
                likelihoodRationale={risk.residual_likelihood_rationale}
                impactLabel="Residual impact rationale"
                likelihoodLabel="Residual likelihood rationale"
                busy={busy === 'residual'}
                hint={`Control effectiveness resolves to ${risk.ce_resolution.effective_ce}, permitting a likelihood reduction of at most ${risk.ce_resolution.max_likelihood_reduction}.`}
                onSubmit={(impact, likelihood, ir, lr) =>
                  run(
                    'residual',
                    () =>
                      api.post(`/risks/${id}/score/residual`, {
                        residual_impact: impact,
                        residual_likelihood: likelihood,
                        residual_impact_rationale: ir,
                        residual_likelihood_rationale: lr,
                      }),
                    'Residual score recorded',
                  )
                }
              />
            )}
          </Card>

          <Card
            className="lg:col-span-2"
            title="Control effectiveness resolution"
            subtitle="Which linked controls counted toward the score, and which did not, with the rule that excluded each one."
          >
            <CEResolution data={risk.ce_resolution} scope={risk.scope_assets ?? []} />
          </Card>
        </div>
      )}

      {tab === 'treatment' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card
            className="lg:col-span-2"
            title="Treatment decision"
            subtitle="Critical risks cannot be accepted (RINV-5). Acceptance is always time-bound and capped by rating (RINV-4)."
          >
            <TreatmentDecisionForm
              risk={risk}
              users={users}
              busy={busy === 'decision'}
              onSubmit={(body) =>
                run('decision', () => api.post(`/risks/${id}/treatment-decision`, body), 'Treatment decision recorded')
              }
            />
          </Card>

          <Card
            title="Readout"
            subtitle="Mandatory at Moderate and above; cannot be bypassed (RINV-6)."
          >
            <div className="space-y-3">
              <label className="flex items-start gap-3 rounded-md border bg-surface-sunken px-3 py-2.5">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-emerald-600"
                  checked={risk.readout_confirmed}
                  onChange={(e) =>
                    patch(
                      {
                        readout_confirmed: e.target.checked,
                        readout_conducted_at: e.target.checked ? new Date().toISOString() : null,
                      },
                      'Readout updated',
                    )
                  }
                />
                <div>
                  <p className="text-sm font-medium text-ink">
                    Risk Owner confirmed the treatment plan at governance readout
                  </p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {risk.readout_conducted_at
                      ? formatDateTime(risk.readout_conducted_at)
                      : 'Not yet conducted'}
                  </p>
                </div>
              </label>
              <Field label="Adjustment rationale">
                <textarea
                  className="field"
                  rows={3}
                  defaultValue={risk.readout_adjustment_rationale ?? ''}
                  onBlur={(e) =>
                    e.target.value !== (risk.readout_adjustment_rationale ?? '') &&
                    patch({ readout_adjustment_rationale: e.target.value }, 'Rationale saved')
                  }
                  placeholder="Any adjustment the forum made to the plan"
                />
              </Field>
            </div>
          </Card>
        </div>
      )}

      {tab === 'links' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Linked controls"
            subtitle="CE is snapshotted at link time (RES-5). Later drift flags the risk rather than silently rescoring it."
            action={
              <button className="btn-ghost btn-sm" onClick={() => setModal('control')}>
                <Plus className="h-3.5 w-3.5" />
                Link
              </button>
            }
            bodyClassName={risk.controls.length ? 'p-0' : undefined}
          >
            {risk.controls.length === 0 ? (
              <Empty title="No controls linked" />
            ) : (
              <ul className="divide-y">
                {risk.controls.map((c: any) => (
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
                    <span
                      className="chip border-line bg-surface-sunken text-ink-faint"
                      title="CE recorded when the link was made"
                    >
                      was {c.ce_at_assessment}
                    </span>
                    <button
                      className="text-ink-faint hover:text-rose-500"
                      onClick={() =>
                        run(
                          'unlink',
                          () => api.del(`/risks/${id}/controls/${c.link_id}`),
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

          <Card
            title="Linked treatments"
            subtitle="RINV-12: every treatment needs GRC Engineer validation and an owner commitment before readout."
            action={
              <button className="btn-ghost btn-sm" onClick={() => setModal('treatment')}>
                <Plus className="h-3.5 w-3.5" />
                Link
              </button>
            }
            bodyClassName={risk.treatments.length ? 'p-0' : undefined}
          >
            {risk.treatments.length === 0 ? (
              <Empty title="No treatments linked" />
            ) : (
              <ul className="divide-y">
                {risk.treatments.map((t: any) => (
                  <li key={t.link_id} className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/treatments/${t.treatment_id}`}
                          className="mono text-ink-faint hover:text-accent"
                        >
                          {t.reference}
                        </Link>
                        <p className="truncate text-sm text-ink">{t.title}</p>
                      </div>
                      <Badge value={t.lifecycle_state} />
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span
                        className={cx(
                          'chip',
                          t.grc_eng_validated
                            ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                            : 'border-line bg-surface-sunken text-ink-faint',
                        )}
                      >
                        GRC validated
                      </span>
                      <span
                        className={cx(
                          'chip',
                          t.owner_committed
                            ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                            : 'border-line bg-surface-sunken text-ink-faint',
                        )}
                      >
                        Owner committed
                      </span>
                      <span className="chip border-line bg-surface-sunken text-ink-faint">
                        Target {formatDate(t.target_date)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'invariants' && (
        <Card
          title="Invariants on this record"
          subtitle="Evaluated live. Every one of these runs before any write to this risk is committed."
        >
          <InvariantList invariants={risk.invariants} />
        </Card>
      )}

      {tab === 'history' && (
        <Card
          title="Phase history"
          subtitle="Append-only. The database rejects UPDATE and DELETE on this table."
          bodyClassName="p-0"
        >
          <ul className="divide-y">
            {risk.history.map((h: any, i: number) => (
              <li key={i} className="px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge value={h.from ?? 'created'} />
                  <span className="text-ink-faint">→</span>
                  <Badge value={h.to} />
                  <span className="mono text-ink-faint">{h.gate}</span>
                  <span className="ml-auto text-xs text-ink-muted">
                    {userName(h.changed_by)} · {formatDateTime(h.created_at)}
                  </span>
                </div>
                {Array.isArray(h.evaluation?.checks) && h.evaluation.checks.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {h.evaluation.checks.map((c: any) => (
                      <li
                        key={c.id}
                        className="chip border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300"
                        title={c.name}
                      >
                        {c.id}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {tab === 'discussion' && (
        <Card title="Discussion">
          <CommentBox
            onSubmit={(body) =>
              run('comment', () => api.post(`/risks/${id}/comments`, { body }), 'Comment added')
            }
          />
          {risk.comments.length === 0 ? (
            <Empty title="No comments yet" />
          ) : (
            <ul className="mt-4 divide-y">
              {risk.comments.map((c: any) => (
                <li key={c.id} className="py-3">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-ink">{userName(c.created_by)}</span>
                    <span className="text-xs text-ink-faint">{formatDateTime(c.created_at)}</span>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-ink-muted">{c.body}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <LinkModal
        open={modal === 'control'}
        onClose={() => setModal(null)}
        title="Link a control objective"
        description="Only Operating controls with non-expired evidence contribute to scoring. Linking a control that does not qualify is allowed; the CE resolution panel will show why it was excluded."
        options={controls
          .filter((c) => !risk.controls.some((rc: any) => rc.objective_id === c.id))
          .map((c) => ({
            id: c.id,
            primary: `${c.reference} — ${c.title}`,
            secondary: `${label(c.lifecycle_state)} · ${c.effective_ce}`,
          }))}
        onSelect={async (cid) => {
          const ok = await run('link', () => api.post(`/risks/${id}/controls`, { id: cid }), 'Control linked')
          if (ok) setModal(null)
        }}
      />

      <LinkModal
        open={modal === 'treatment'}
        onClose={() => setModal(null)}
        title="Link a treatment"
        description="SEP-2: the Risk Owner cannot also own the treatment. The decision maker and the executor must be different people."
        options={treatments
          .filter((t) => !risk.treatments.some((rt: any) => rt.treatment_id === t.id))
          .map((t) => ({
            id: t.id,
            primary: `${t.reference} — ${t.title}`,
            secondary: `${label(t.lifecycle_state)} · target ${formatDate(t.target_date)}`,
          }))}
        onSelect={async (tid) => {
          const ok = await run(
            'link',
            () => api.post(`/risks/${id}/treatments`, { id: tid }),
            'Treatment linked',
          )
          if (ok) setModal(null)
        }}
      />
    </>
  )
}

function ScoreForm({
  impact,
  likelihood,
  impactRationale,
  likelihoodRationale,
  impactLabel,
  likelihoodLabel,
  onSubmit,
  disabled,
  busy,
  hint,
}: {
  impact: number | null
  likelihood: number | null
  impactRationale: string | null
  likelihoodRationale: string | null
  impactLabel: string
  likelihoodLabel: string
  onSubmit: (i: number, l: number, ir: string, lr: string) => void
  disabled?: boolean
  busy?: boolean
  hint?: string
}) {
  const [i, setI] = useState(impact ?? 3)
  const [l, setL] = useState(likelihood ?? 3)
  const [ir, setIr] = useState(impactRationale ?? '')
  const [lr, setLr] = useState(likelihoodRationale ?? '')

  useEffect(() => {
    setI(impact ?? 3)
    setL(likelihood ?? 3)
    setIr(impactRationale ?? '')
    setLr(likelihoodRationale ?? '')
  }, [impact, likelihood, impactRationale, likelihoodRationale])

  const score = i * l
  const rating =
    score >= 20 ? 'Critical' : score >= 15 ? 'High' : score >= 10 ? 'Moderate' : score >= 5 ? 'Moderate-Low' : 'Low'

  return (
    <div className="space-y-4">
      {hint && (
        <p className="rounded-lg border bg-surface-sunken px-3 py-2 text-xs text-ink-muted">
          {hint}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Impact (1-5)">
          <select
            className="field"
            value={i}
            disabled={disabled}
            onChange={(e) => setI(Number(e.target.value))}
          >
            {[
              [1, 'Minimal'],
              [2, 'Low'],
              [3, 'Moderate'],
              [4, 'High'],
              [5, 'Critical'],
            ].map(([v, name]) => (
              <option key={v} value={v}>
                {v} — {name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Likelihood (1-5)">
          <select
            className="field"
            value={l}
            disabled={disabled}
            onChange={(e) => setL(Number(e.target.value))}
          >
            {[
              [1, 'Rare'],
              [2, 'Unlikely'],
              [3, 'Possible'],
              [4, 'Likely'],
              [5, 'Almost Certain'],
            ].map(([v, name]) => (
              <option key={v} value={v}>
                {v} — {name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="flex items-center gap-3 rounded-lg border bg-surface-sunken px-4 py-3">
        <span className="text-3xl font-semibold tabular-nums text-ink">{score}</span>
        <Badge value={rating} />
        <span className="ml-auto text-xs text-ink-muted">impact × likelihood (CALC-1)</span>
      </div>

      <Field label={impactLabel}>
        <textarea
          className="field"
          rows={2}
          value={ir}
          disabled={disabled}
          onChange={(e) => setIr(e.target.value)}
        />
      </Field>
      <Field label={likelihoodLabel}>
        <textarea
          className="field"
          rows={2}
          value={lr}
          disabled={disabled}
          onChange={(e) => setLr(e.target.value)}
        />
      </Field>

      <button
        className="btn-primary w-full"
        disabled={disabled || busy}
        onClick={() => onSubmit(i, l, ir, lr)}
      >
        Save score
      </button>
    </div>
  )
}

function TreatmentDecisionForm({
  risk,
  users,
  onSubmit,
  busy,
}: {
  risk: any
  users: any[]
  onSubmit: (body: Record<string, unknown>) => void
  busy?: boolean
}) {
  const [strategy, setStrategy] = useState(risk.treatment_strategy ?? 'Mitigate')
  const [expiry, setExpiry] = useState(risk.acceptance_expiry_date ?? '')
  const [rationale, setRationale] = useState(risk.acceptance_rationale ?? '')
  const [approver, setApprover] = useState(risk.acceptance_approved_by ?? '')
  const [mapping, setMapping] = useState(risk.control_framework_mapping ?? '')
  const [transfer, setTransfer] = useState(risk.transfer_description ?? '')
  const [avoid, setAvoid] = useState(risk.avoidance_description ?? '')

  const criticalBlocked = risk.inherent_rating === 'Critical'

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-4">
        {['Mitigate', 'Accept', 'Transfer', 'Avoid'].map((s) => {
          const blocked = s === 'Accept' && criticalBlocked
          return (
            <button
              key={s}
              onClick={() => !blocked && setStrategy(s)}
              disabled={blocked}
              title={blocked ? 'RINV-5: a Critical risk cannot be accepted' : undefined}
              className={cx(
                'rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors',
                strategy === s
                  ? 'border-accent bg-accent text-white'
                  : blocked
                    ? 'cursor-not-allowed border-dashed text-ink-faint opacity-60'
                    : 'bg-surface-sunken text-ink-muted hover:text-ink',
              )}
            >
              {s}
              {blocked && <Lock className="ml-1.5 inline h-3 w-3" />}
            </button>
          )
        })}
      </div>

      {criticalBlocked && (
        <p className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          RINV-5: this risk is rated Critical, so Accept is not an available decision. The API
          refuses it regardless of what the UI shows.
        </p>
      )}

      {strategy === 'Mitigate' && (
        <Field
          label="Control framework mapping"
          hint="Required for a Mitigate decision at the Phase 4 gate."
        >
          <input
            className="field"
            value={mapping}
            onChange={(e) => setMapping(e.target.value)}
            placeholder="ISO 27001 A.5.17; NIST 800-53 IA-2(1)"
          />
        </Field>
      )}

      {strategy === 'Accept' && (
        <div className="space-y-3">
          <Field
            label="Acceptance expiry"
            hint="RINV-4: acceptance is always time-bound, and the window is capped by rating."
          >
            <input
              className="field"
              type="date"
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
            />
          </Field>
          <Field label="Acceptance rationale">
            <textarea
              className="field"
              rows={2}
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
            />
          </Field>
          <Field label="Approved by">
            <select className="field" value={approver} onChange={(e) => setApprover(e.target.value)}>
              <option value="">Select approver</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name} — {u.seniority}
                </option>
              ))}
            </select>
          </Field>
        </div>
      )}

      {strategy === 'Transfer' && (
        <Field label="Transfer description">
          <textarea
            className="field"
            rows={3}
            value={transfer}
            onChange={(e) => setTransfer(e.target.value)}
            placeholder="Insurance, contractual transfer, or outsourcing arrangement"
          />
        </Field>
      )}

      {strategy === 'Avoid' && (
        <Field label="Avoidance description">
          <textarea
            className="field"
            rows={3}
            value={avoid}
            onChange={(e) => setAvoid(e.target.value)}
            placeholder="What activity is being discontinued or redesigned"
          />
        </Field>
      )}

      <button
        className="btn-primary"
        disabled={busy}
        onClick={() =>
          onSubmit({
            treatment_strategy: strategy,
            acceptance_expiry_date: strategy === 'Accept' ? expiry || null : null,
            acceptance_rationale: rationale || null,
            acceptance_approved_by: approver || null,
            control_framework_mapping: mapping || null,
            transfer_description: transfer || null,
            avoidance_description: avoid || null,
          })
        }
      >
        Record decision
      </button>
    </div>
  )
}

function LinkModal({
  open,
  onClose,
  title,
  description,
  options,
  onSelect,
}: {
  open: boolean
  onClose: () => void
  title: string
  description: string
  options: { id: string; primary: string; secondary: string }[]
  onSelect: (id: string) => void
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} description={description}>
      {options.length === 0 ? (
        <Empty title="Nothing available to link" />
      ) : (
        <ul className="max-h-96 space-y-1 overflow-y-auto">
          {options.map((o) => (
            <li key={o.id}>
              <button
                className="flex w-full items-center gap-2 rounded-lg border bg-surface-sunken px-3 py-2.5 text-left hover:border-accent"
                onClick={() => onSelect(o.id)}
              >
                <Link2 className="h-4 w-4 shrink-0 text-ink-faint" />
                <div className="min-w-0">
                  <p className="truncate text-sm text-ink">{o.primary}</p>
                  <p className="text-xs text-ink-muted">{o.secondary}</p>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}

function CommentBox({ onSubmit }: { onSubmit: (body: string) => Promise<boolean> }) {
  const [body, setBody] = useState('')
  return (
    <div className="flex gap-2">
      <textarea
        className="field"
        rows={2}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Add a note to this risk"
      />
      <button
        className="btn-primary self-end"
        disabled={!body.trim()}
        onClick={async () => {
          if (await onSubmit(body)) setBody('')
        }}
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  )
}

/** Add and remove the assets a risk concerns.
 *
 * Removal is the interesting direction. Taking an asset out of scope widens
 * what counts toward control effectiveness, so a residual reduction that only
 * the removed asset's control justified stops being earned. The API runs the
 * invariants after the delete and rolls the whole thing back if they refuse,
 * which is why this does not try to warn beforehand: the engine gives a better
 * answer than a guess would.
 */
function ScopeEditor({
  scope,
  assets,
  busy,
  onAdd,
  onRemove,
}: {
  scope: { id: string; name: string | null }[]
  assets: any[]
  busy: boolean
  onAdd: (assetId: string) => void
  onRemove: (assetId: string) => void
}) {
  const inScope = new Set(scope.map((a) => a.id))
  const available = assets.filter((a) => !inScope.has(a.id))

  return (
    <div className="space-y-3">
      {scope.length === 0 ? (
        <p className="text-sm text-ink-faint">
          No assets named. Control effectiveness is resolved across every deployment of
          every linked control, wherever it runs. That is right for an organisational
          risk and wrong for most others.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {scope.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-2 rounded-md border bg-surface-sunken px-3 py-2 text-sm"
            >
              <span className="text-ink">{a.name ?? a.id}</span>
              <button
                type="button"
                className="btn-ghost ml-auto shrink-0 text-xs"
                disabled={busy}
                onClick={() => onRemove(a.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {available.length > 0 && (
        <select
          className="field"
          value=""
          disabled={busy}
          onChange={(e) => e.target.value && onAdd(e.target.value)}
        >
          <option value="">Add an asset...</option>
          {available.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
              {a.tier ? ', ' + String(a.tier).replace('_', ' ') : ''}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}
