import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Link2,
  Paperclip,
  Plus,
  RotateCcw,
  Send,
  ShieldCheck,
  X,
} from 'lucide-react'
import { api, ApiError, getStoredUser } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Badge, Card, Empty, Field, Modal, PageLoader, Tabs, useToast } from '../components/ui'
import { GatePanel, InvariantList } from '../components/governance'
import {
  ClassificationBadge,
  ComponentRow,
  EnvironmentPanel,
  TrustZoneBadge,
} from '../components/threat'
import { cx, formatDate, formatDateTime, label } from '../lib/format'

export default function ThreatModelDetail() {
  const { id = '' } = useParams()
  const me = getStoredUser()
  const [tm, setTm] = useState<any>(null)
  const [ref, setRef] = useState<any>(null)
  const [deployments, setDeployments] = useState<any[]>([])
  const [risks, setRisks] = useState<any[]>([])
  const [assets, setAssets] = useState<any[]>([])
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
    api.get<any[]>('/assets').then(setAssets).catch(() => undefined)
    api.get<any[]>('/risks').then(setRisks).catch(() => undefined)
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
                a.deployments.map((d: any) => ({
                  ...d,
                  objective: o.reference,
                  family: o.family,
                })),
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

  const run = async (key: string, fn: () => Promise<any>, okTitle: string, okBody?: string) => {
    setBusy(key)
    try {
      const result = await fn()
      if (result && typeof result === 'object' && 'scenarios' in result) setTm(result)
      else await load()
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
  const coverage = tm.context?.component_coverage ?? {}
  const blockingGaps = tm.context?.blocking_gaps ?? []

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
            {tm.sensitive_components > 0 && (
              <span className="chip border-purple-300 bg-purple-50 text-purple-700 dark:border-purple-900 dark:bg-purple-950/50 dark:text-purple-300">
                {tm.sensitive_components} sensitive component
                {tm.sensitive_components === 1 ? '' : 's'}
              </span>
            )}
            {tm.risk_linked_count > 0 && (
              <span className="chip border-line bg-surface-sunken text-ink-muted">
                {tm.risk_linked_count} linked to the register
              </span>
            )}
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

      {blockingGaps.length > 0 && (
        <div className="mb-5 flex gap-3 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 dark:border-rose-900 dark:bg-rose-950/40">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
          <div>
            <p className="text-sm font-medium text-rose-900 dark:text-rose-200">
              {blockingGaps.length} gap{blockingGaps.length === 1 ? '' : 's'} blocking sign-off
            </p>
            <ul className="mt-1 space-y-0.5 text-sm text-rose-800 dark:text-rose-300">
              {blockingGaps.map((g: any, i: number) => (
                <li key={i}>{g.detail}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="mb-5">
        <Tabs
          tabs={[
            { id: 'scenarios', label: 'Scenarios', count: tm.scenarios.length },
            { id: 'decomposition', label: 'Decomposition', count: tm.components.length },
            {
              id: 'environment',
              label: 'Environment',
              count: tm.context?.gaps?.length ?? 0,
            },
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
          subtitle="Identified against the architecture as designed. Existing controls inform where to look; they never resolve a scenario on their own (TINV-7)."
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
                  ? 'Decompose the system first.'
                  : 'Identify threats against the decomposed components.'
              }
            />
          ) : (
            <ul className="divide-y">
              {tm.scenarios.map((s: any) => (
                <ScenarioCard
                  key={s.id}
                  scenario={s}
                  userName={userName}
                  busy={busy}
                  onAction={(type) => setModal({ type, scenario: s })}
                  onComment={(body) =>
                    run(
                      'comment-' + s.id,
                      () =>
                        api.post(`/threat-models/${id}/scenarios/${s.id}/comments`, { body }),
                      'Comment added',
                    )
                  }
                  onUnlinkMitigation={(linkId) =>
                    run(
                      'unmit-' + linkId,
                      () =>
                        api.del(
                          `/threat-models/${id}/scenarios/${s.id}/mitigations/${linkId}`,
                        ),
                      'Mitigation unlinked',
                      'The scenario returns to Identified: Mitigated is an assertion backed by a live control, not by ambient posture.',
                    )
                  }
                  onUnlinkRisk={(linkId) =>
                    run(
                      'unrisk-' + linkId,
                      () => api.del(`/threat-models/${id}/scenarios/${s.id}/risks/${linkId}`),
                      'Risk link removed',
                    )
                  }
                />
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'decomposition' && (
        <Card
          title="Decomposition"
          subtitle="What each component handles and where it sits. Both determine what a compromise costs, so both are enforced attributes rather than prose."
          action={
            <button className="btn-ghost btn-sm" onClick={() => setModal({ type: 'component' })}>
              <Plus className="h-3.5 w-3.5" />
              Component
            </button>
          }
        >
          {tm.components.length === 0 ? (
            <Empty title="No components defined" />
          ) : (
            <ul className="space-y-2">
              {tm.components.map((c: any) => (
                <ComponentRow
                  key={c.id}
                  component={c}
                  coverage={coverage[c.id]}
                  onEdit={() => setModal({ type: 'component', component: c })}
                  onAddScenario={() => setModal({ type: 'scenario', component: c })}
                />
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'environment' && <EnvironmentPanel context={tm.context} />}

      {tab === 'lifecycle' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Available transitions"
            subtitle="Review to Active is where the decomposition rules land: every sensitive component zoned (TINV-9) and analysed (TINV-11), every resolution reasoned (TINV-10), two independent signatures (TINV-2)."
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

      {/* ---------------------------------------------------------- modals */}

      <ComponentModal
        open={modal?.type === 'component'}
        component={modal?.component}
        refData={ref}
        assets={assets}
        components={tm.components}
        onClose={() => setModal(null)}
        onSubmit={async (body) => {
          const ok = modal?.component
            ? await run(
                'component',
                () =>
                  api.patch(
                    `/threat-models/${id}/components/${modal.component.id}`,
                    body,
                  ),
                'Component updated',
              )
            : await run(
                'component',
                () => api.post(`/threat-models/${id}/components`, body),
                'Component added',
              )
          if (ok) setModal(null)
        }}
      />

      <ScenarioModal
        open={modal?.type === 'scenario'}
        refData={ref}
        components={tm.components}
        preselect={modal?.component}
        coverage={coverage}
        onClose={() => setModal(null)}
        onSubmit={async (body) => {
          const ok = await run(
            'scenario',
            () => api.post(`/threat-models/${id}/scenarios`, body),
            'Scenario added',
          )
          if (ok) setModal(null)
        }}
      />

      <MitigateModal
        open={modal?.type === 'mitigate'}
        deployments={deployments}
        scenario={modal?.scenario}
        onClose={() => setModal(null)}
        onSubmit={async (deploymentId) => {
          const ok = await run(
            'mitigate',
            () =>
              api.post(
                `/threat-models/${id}/scenarios/${modal.scenario.id}/mitigate`,
                { deployment_id: deploymentId, effectiveness_assurance: 'Fully_Mitigated' },
              ),
            'Scenario mitigated',
          )
          if (ok) setModal(null)
        }}
      />

      <AcceptModal
        open={modal?.type === 'accept'}
        onClose={() => setModal(null)}
        onSubmit={async (body) => {
          const ok = await run(
            'accept',
            () =>
              api.post(`/threat-models/${id}/scenarios/${modal.scenario.id}/accept`, body),
            'Scenario accepted',
          )
          if (ok) setModal(null)
        }}
      />

      <LinkRiskModal
        open={modal?.type === 'link-risk'}
        risks={risks}
        refData={ref}
        scenario={modal?.scenario}
        contextRisks={tm.context?.risk_posture?.risks ?? []}
        onClose={() => setModal(null)}
        onSubmit={async (body) => {
          const ok = await run(
            'link-risk',
            () =>
              api.post(`/threat-models/${id}/scenarios/${modal.scenario.id}/risks`, body),
            'Linked to the register',
            'No duplicate record was created; the scenario references the existing exposure (TINV-8).',
          )
          if (ok) setModal(null)
        }}
      />

      <EvidenceModal
        open={modal?.type === 'evidence'}
        refData={ref}
        onClose={() => setModal(null)}
        onSubmit={async (body) => {
          const ok = await run(
            'evidence',
            () =>
              api.post(
                `/threat-models/${id}/scenarios/${modal.scenario.id}/evidence`,
                body,
              ),
            'Evidence attached',
          )
          if (ok) setModal(null)
        }}
      />

      <ReopenModal
        open={modal?.type === 'reopen'}
        scenario={modal?.scenario}
        onClose={() => setModal(null)}
        onSubmit={async (rationale) => {
          const ok = await run(
            'reopen',
            () =>
              api.post(`/threat-models/${id}/scenarios/${modal.scenario.id}/reopen`, {
                rationale,
              }),
            'Scenario reopened',
          )
          if (ok) setModal(null)
        }}
      />

      <PromoteModal
        open={modal?.type === 'promote'}
        scenario={modal?.scenario}
        users={users}
        onClose={() => setModal(null)}
        onSubmit={async (body) => {
          setBusy('promote')
          try {
            const res = await api.post<any>(
              `/threat-models/${id}/scenarios/${modal.scenario.id}/promote`,
              body,
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
      />
    </>
  )
}

/* ------------------------------------------------------------- scenario card */

function ScenarioCard({
  scenario: s,
  userName,
  busy,
  onAction,
  onComment,
  onUnlinkMitigation,
  onUnlinkRisk,
}: {
  scenario: any
  userName: (id: string | null) => string
  busy: string | null
  onAction: (type: string) => void
  onComment: (body: string) => Promise<boolean>
  onUnlinkMitigation: (linkId: string) => void
  onUnlinkRisk: (linkId: string) => void
}) {
  const [open, setOpen] = useState<'none' | 'discussion' | 'evidence'>('none')
  const [comment, setComment] = useState('')

  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mono text-ink-faint">{s.reference}</span>
        <Badge value={s.category} />
        <Badge value={s.inherent_severity} />
        <Badge value={s.status} />
        {s.carried_by_register && (
          <span className="chip border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300">
            in the register
          </span>
        )}
        <span className="ml-auto flex items-center gap-2 text-xs text-ink-muted">
          on {s.component_name}
          <ClassificationBadge
            classification={s.component_classification}
            sensitive={s.component_sensitive}
          />
        </span>
      </div>

      <p className="mt-1.5 text-sm text-ink">{s.description}</p>

      {s.status_rationale && (
        <p className="mt-1.5 rounded-md bg-surface-sunken px-3 py-2 text-xs leading-relaxed text-ink-muted">
          {s.status_rationale}
        </p>
      )}

      {s.reopened_reason && (
        <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          Re-opened {formatDate(s.reopened_at)}: {s.reopened_reason}
        </p>
      )}

      {/* mitigating controls */}
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
              <ShieldCheck className="h-3 w-3 shrink-0 text-ink-faint" />
              <span className="mono">{m.deployment_reference}</span>
              <span className="text-ink-muted">{m.asset}</span>
              <Badge value={m.deployment_status} />
              {!m.live && (
                <span className="font-medium text-rose-700 dark:text-rose-300">
                  not operating — does not mitigate (TINV-4)
                </span>
              )}
              <button
                className="ml-auto text-ink-faint hover:text-rose-500"
                onClick={() => onUnlinkMitigation(m.link_id)}
                title="Unlink this control"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* register linkage */}
      {s.risk_links.length > 0 && (
        <ul className="mt-2 space-y-1">
          {s.risk_links.map((rl: any) => (
            <li
              key={rl.link_id}
              className="rounded-md border border-sky-200 bg-sky-50/60 px-3 py-2 text-xs dark:border-sky-900 dark:bg-sky-950/20"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Link2 className="h-3 w-3 shrink-0 text-sky-600" />
                <Link to={`/risks/${rl.risk_id}`} className="mono hover:text-accent">
                  {rl.reference}
                </Link>
                <span className="text-ink-muted">{label(rl.link_type)}</span>
                <Badge value={rl.reported_rating} />
                {rl.residual_score_locked && (
                  <span className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300">
                    residual locked
                  </span>
                )}
                <button
                  className="ml-auto text-ink-faint hover:text-rose-500"
                  onClick={() => onUnlinkRisk(rl.link_id)}
                  title="Remove this link"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              {rl.rationale && (
                <p className="mt-1 pl-5 leading-relaxed text-ink-muted">{rl.rationale}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {s.promoted_risk_id && s.risk_links.length === 0 && (
        <Link
          to={`/risks/${s.promoted_risk_id}`}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent"
        >
          <ArrowUpRight className="h-3.5 w-3.5" />
          Promoted to the risk register
        </Link>
      )}

      {/* actions */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {s.status === 'Identified' && (
          <>
            <button className="btn-ghost btn-sm" onClick={() => onAction('mitigate')}>
              Link a mitigating control
            </button>
            <button
              className="btn-ghost btn-sm"
              disabled={s.requires_promotion}
              title={
                s.requires_promotion
                  ? 'TINV-3: at or above the promotion threshold, local acceptance is not a legal end state'
                  : undefined
              }
              onClick={() => onAction('accept')}
            >
              Accept locally
            </button>
            <button className="btn-ghost btn-sm" onClick={() => onAction('link-risk')}>
              Link to an existing risk
            </button>
            <button className="btn-ghost btn-sm" onClick={() => onAction('promote')}>
              Promote to a new risk
            </button>
          </>
        )}
        {s.status !== 'Identified' && s.status !== 'Promoted_To_Risk' && (
          <button className="btn-ghost btn-sm" onClick={() => onAction('reopen')}>
            <RotateCcw className="h-3.5 w-3.5" />
            Reopen
          </button>
        )}
        <button className="btn-ghost btn-sm" onClick={() => onAction('evidence')}>
          <Paperclip className="h-3.5 w-3.5" />
          Attach evidence
        </button>
        <button
          className={cx('btn-ghost btn-sm', open === 'discussion' && 'border-accent text-accent')}
          onClick={() => setOpen(open === 'discussion' ? 'none' : 'discussion')}
        >
          Discussion ({s.comments.length})
        </button>
        <button
          className={cx('btn-ghost btn-sm', open === 'evidence' && 'border-accent text-accent')}
          onClick={() => setOpen(open === 'evidence' ? 'none' : 'evidence')}
        >
          Evidence ({s.evidence.length})
        </button>
      </div>

      {open === 'discussion' && (
        <div className="mt-3 rounded-lg border bg-surface-sunken p-3">
          <div className="flex gap-2">
            <textarea
              className="field"
              rows={2}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Add a note to this scenario"
            />
            <button
              className="btn-primary self-end"
              disabled={!comment.trim() || busy === 'comment-' + s.id}
              onClick={async () => {
                if (await onComment(comment)) setComment('')
              }}
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          {s.comments.length > 0 && (
            <ul className="mt-3 divide-y">
              {s.comments.map((c: any) => (
                <li key={c.id} className="py-2">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-ink">
                      {userName(c.created_by)}
                    </span>
                    <span className="text-xs text-ink-faint">
                      {formatDateTime(c.created_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 whitespace-pre-wrap text-sm text-ink-muted">{c.body}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {open === 'evidence' && (
        <div className="mt-3 rounded-lg border bg-surface-sunken p-3">
          <p className="mb-2 text-xs text-ink-muted">
            Append-only. The database rejects UPDATE and DELETE, so a correction supersedes
            rather than rewrites (TINV-10).
          </p>
          {s.evidence.length === 0 ? (
            <Empty title="No evidence attached" />
          ) : (
            <ul className="divide-y">
              {s.evidence.map((e: any) => (
                <li key={e.id} className="py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Paperclip className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                    <span className="text-sm font-medium text-ink">{e.title}</span>
                    {e.evidence_type && (
                      <span className="chip border-line bg-surface text-ink-muted">
                        {label(e.evidence_type)}
                      </span>
                    )}
                    {e.supports && (
                      <span className="chip border-line bg-surface text-ink-faint">
                        supports {label(e.supports)}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-ink-faint">
                      {userName(e.created_by)} · {formatDateTime(e.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 pl-6 text-xs leading-relaxed text-ink-muted">
                    {e.evidence_ref}
                  </p>
                  {e.notes && <p className="mt-0.5 pl-6 text-xs text-ink-faint">{e.notes}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  )
}

/* -------------------------------------------------------------------- modals */

function ComponentModal({
  open,
  component,
  refData,
  assets,
  components,
  onClose,
  onSubmit,
}: {
  open: boolean
  component?: any
  refData: any
  assets: any[]
  components: any[]
  onClose: () => void
  onSubmit: (body: any) => void
}) {
  const [form, setForm] = useState<any>({})
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!open) {
      setReady(false)
      return
    }
    setForm(
      component
        ? {
            name: component.name,
            component_type: component.component_type,
            description: component.description ?? '',
            data_classification: component.data_classification ?? '',
            data_types: component.data_types ?? [],
            trust_zone: component.trust_zone ?? '',
            exposure: component.exposure ?? '',
            attack_surface_id: component.attack_surface_id ?? '',
            source_component_id: component.source_component_id ?? '',
            target_component_id: component.target_component_id ?? '',
          }
        : {
            name: '',
            component_type: refData?.component_types?.[0] ?? 'Process',
            description: '',
            data_classification: '',
            data_types: [],
            trust_zone: '',
            exposure: '',
            attack_surface_id: '',
            source_component_id: '',
            target_component_id: '',
          },
    )
    setReady(true)
  }, [open, component, refData])

  if (!ready) return null
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))
  const classifications: string[] = refData?.data_classifications ?? []
  const threshold = refData?.sensitive_threshold
  const sensitive =
    form.data_classification &&
    classifications.indexOf(form.data_classification) >= classifications.indexOf(threshold)
  const isFlow = form.component_type === 'Data_Flow'

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={component ? `Edit ${component.name}` : 'New component'}
      description="What a component handles and where it sits determine what its compromise costs. Both are enforced attributes, not prose."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const body: any = { ...form }
          Object.keys(body).forEach((k) => {
            if (body[k] === '' || (Array.isArray(body[k]) && body[k].length === 0)) delete body[k]
          })
          onSubmit(body)
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <input
              className="field"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              required
            />
          </Field>
          <Field label="Type">
            <select
              className="field"
              value={form.component_type}
              onChange={(e) => set('component_type', e.target.value)}
            >
              {(refData?.component_types ?? []).map((t: string) => (
                <option key={t} value={t}>
                  {label(t)}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Description">
          <textarea
            className="field"
            rows={2}
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </Field>

        <div className="rounded-lg border bg-surface-sunken p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-muted">
            What it handles
          </p>
          <div className="space-y-3">
            <Field
              label="Data classification"
              hint={
                sensitive
                  ? `At or above ${threshold}: this component must declare a trust zone (TINV-9) and carry at least one scenario before sign-off (TINV-11).`
                  : undefined
              }
            >
              <select
                className="field"
                value={form.data_classification}
                onChange={(e) => set('data_classification', e.target.value)}
              >
                <option value="">Unclassified</option>
                {classifications.map((c: string) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Data types">
              <div className="flex flex-wrap gap-1.5">
                {(refData?.data_types ?? []).map((d: string) => {
                  const on = (form.data_types ?? []).includes(d)
                  return (
                    <button
                      key={d}
                      type="button"
                      onClick={() =>
                        set(
                          'data_types',
                          on
                            ? form.data_types.filter((x: string) => x !== d)
                            : [...(form.data_types ?? []), d],
                        )
                      }
                      className={cx(
                        'chip',
                        on
                          ? 'border-accent bg-accent text-white'
                          : 'border-line bg-surface text-ink-muted',
                      )}
                    >
                      {label(d)}
                    </button>
                  )
                })}
              </div>
            </Field>
          </div>
        </div>

        <div className="rounded-lg border bg-surface-sunken p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Where it sits
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Trust zone">
              <select
                className="field"
                value={form.trust_zone}
                onChange={(e) => set('trust_zone', e.target.value)}
                required={!!sensitive}
              >
                <option value="">Not declared</option>
                {(refData?.trust_zones ?? []).map((z: any) => (
                  <option key={z.id} value={z.id}>
                    {z.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Exposure">
              <select
                className="field"
                value={form.exposure}
                onChange={(e) => set('exposure', e.target.value)}
              >
                <option value="">Not declared</option>
                {(refData?.exposure_levels ?? []).map((x: string) => (
                  <option key={x} value={x}>
                    {label(x)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field
            label="Asset"
            className="mt-3"
            hint="Defaults to the model's asset. Set it when a component lives somewhere else, which is where cross-boundary flows get interesting."
          >
            <select
              className="field"
              value={form.attack_surface_id}
              onChange={(e) => set('attack_surface_id', e.target.value)}
            >
              <option value="">Inherit from the model</option>
              {assets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </Field>

          {isFlow && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Flows from">
                <select
                  className="field"
                  value={form.source_component_id}
                  onChange={(e) => set('source_component_id', e.target.value)}
                >
                  <option value="">—</option>
                  {components
                    .filter((c) => c.id !== component?.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Flows to">
                <select
                  className="field"
                  value={form.target_component_id}
                  onChange={(e) => set('target_component_id', e.target.value)}
                >
                  <option value="">—</option>
                  {components
                    .filter((c) => c.id !== component?.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                </select>
              </Field>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t pt-4">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={!form.name?.trim()}>
            {component ? 'Save changes' : 'Add component'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ScenarioModal({
  open,
  refData,
  components,
  preselect,
  coverage,
  onClose,
  onSubmit,
}: {
  open: boolean
  refData: any
  components: any[]
  preselect?: any
  coverage: any
  onClose: () => void
  onSubmit: (body: any) => void
}) {
  const [componentId, setComponentId] = useState('')
  const [category, setCategory] = useState('')

  useEffect(() => {
    if (open) {
      setComponentId(preselect?.id ?? components[0]?.id ?? '')
      setCategory(refData?.stride_categories?.[0] ?? '')
    }
  }, [open, preselect, components, refData])

  const cov = coverage?.[componentId]
  const gapForCategory =
    cov && category && cov.stride_categories_without_control?.includes(category)

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Identify a threat"
      description="Score severity against the architecture as designed. Existing controls tell you where to look; they do not change what you find (TINV-7)."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const f = new FormData(e.target as HTMLFormElement)
          onSubmit({
            component_id: componentId,
            category,
            description: f.get('description'),
            inherent_severity: f.get('inherent_severity'),
          })
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Component">
            <select
              className="field"
              value={componentId}
              onChange={(e) => setComponentId(e.target.value)}
            >
              {components.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({label(c.component_type)})
                </option>
              ))}
            </select>
          </Field>
          <Field label="STRIDE category">
            <select
              className="field"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {(refData?.stride_categories ?? []).map((c: string) => (
                <option key={c} value={c}>
                  {label(c)}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {cov && (
          <div
            className={cx(
              'rounded-lg border px-3 py-2.5 text-xs leading-relaxed',
              gapForCategory
                ? 'border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-900 dark:bg-orange-950/30 dark:text-orange-300'
                : 'bg-surface-sunken text-ink-muted',
            )}
          >
            {gapForCategory ? (
              <>
                <strong>No control family present</strong> for {label(category)} on this
                component's asset. That is a reason to look harder here, not evidence that a
                threat exists.
              </>
            ) : (
              <>
                {cov.effective_count} control{cov.effective_count === 1 ? '' : 's'} operating on
                this component's asset ({cov.families_present.map(label).join(', ') || 'none'}).
                Informative only: identify the threat regardless, then link a control if one
                genuinely addresses it.
              </>
            )}
          </div>
        )}

        <Field label="Description">
          <textarea className="field" name="description" rows={3} required />
        </Field>
        <Field
          label="Inherent severity"
          hint="Scored against the architecture as designed, with no credit for controls currently in place."
        >
          <select className="field" name="inherent_severity" defaultValue="Medium">
            {(refData?.severities ?? []).map((s: string) => (
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
  )
}

function MitigateModal({
  open,
  deployments,
  scenario,
  onClose,
  onSubmit,
}: {
  open: boolean
  deployments: any[]
  scenario: any
  onClose: () => void
  onSubmit: (deploymentId: string) => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Link a mitigating control"
      description="TINV-4: only a deployment that is Active or Degraded can mitigate. TINV-7: this link is the assertion that makes the scenario Mitigated; ambient presence on the asset is not."
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
                onClick={() => onSubmit(d.id)}
              >
                <span className="mono text-ink-faint">{d.objective}</span>
                <span className="mono text-ink-faint">{d.reference}</span>
                <span className="text-sm text-ink">{d.asset_name}</span>
                <span className="chip border-line bg-surface text-ink-muted">
                  {label(d.family)}
                </span>
                <Badge value={d.deployment_status} />
                <Badge value={d.ce_rating} />
                {!live && <span className="ml-auto text-xs text-ink-faint">not operating</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </Modal>
  )
}

function LinkRiskModal({
  open,
  risks,
  refData,
  scenario,
  contextRisks,
  onClose,
  onSubmit,
}: {
  open: boolean
  risks: any[]
  refData: any
  scenario: any
  contextRisks: any[]
  onClose: () => void
  onSubmit: (body: any) => void
}) {
  const [riskId, setRiskId] = useState('')
  const [linkType, setLinkType] = useState('Represents')
  const [rationale, setRationale] = useState('')

  useEffect(() => {
    if (open) {
      setRiskId('')
      setLinkType('Represents')
      setRationale('')
    }
  }, [open])

  const onAsset = new Set(contextRisks.map((r: any) => r.id))
  const sorted = [...risks].sort((a, b) => {
    const aOn = onAsset.has(a.id) ? 0 : 1
    const bOn = onAsset.has(b.id) ? 0 : 1
    return aOn - bOn || (b.reported_score ?? 0) - (a.reported_score ?? 0)
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Link to an existing risk"
      description="Most threats on a mature system map to exposure the register already carries. Referencing it keeps one record; promoting would create a duplicate (TINV-8)."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit({ risk_id: riskId, link_type: linkType, rationale: rationale || null })
        }}
      >
        <Field label="Relationship">
          <select
            className="field"
            value={linkType}
            onChange={(e) => setLinkType(e.target.value)}
          >
            {(refData?.risk_link_types ?? []).map((t: any) => (
              <option key={t.id} value={t.id}>
                {t.label}
                {t.resolves_scenario ? ' — resolves this scenario' : ' — contributory only'}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Risk">
          <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border p-1.5">
            {sorted.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setRiskId(r.id)}
                className={cx(
                  'flex w-full flex-wrap items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm',
                  riskId === r.id
                    ? 'bg-accent-soft text-accent'
                    : 'hover:bg-surface-sunken',
                )}
              >
                <span className="mono text-ink-faint">{r.reference}</span>
                <span className="min-w-0 flex-1 truncate text-ink">{r.title}</span>
                {onAsset.has(r.id) && (
                  <span className="chip border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300">
                    on this asset
                  </span>
                )}
                <Badge value={r.reported_rating} />
              </button>
            ))}
          </div>
        </Field>

        <Field label="Rationale" hint="Why this threat maps onto that exposure.">
          <textarea
            className="field"
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
        </Field>

        <div className="flex justify-end border-t pt-4">
          <button className="btn-primary" disabled={!riskId}>
            Link
          </button>
        </div>
      </form>
    </Modal>
  )
}

function EvidenceModal({
  open,
  refData,
  onClose,
  onSubmit,
}: {
  open: boolean
  refData: any
  onClose: () => void
  onSubmit: (body: any) => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Attach evidence"
      description="Append-only. The database rejects UPDATE and DELETE, so a correction supersedes rather than rewrites (TINV-10)."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const f = new FormData(e.target as HTMLFormElement)
          onSubmit({
            title: f.get('title'),
            evidence_ref: f.get('evidence_ref'),
            evidence_type: f.get('evidence_type') || null,
            supports: f.get('supports') || null,
            notes: f.get('notes') || null,
          })
        }}
      >
        <Field label="Title">
          <input className="field" name="title" required />
        </Field>
        <Field
          label="Reference"
          hint="A pointer to the artefact: a scan result, design review, ticket, or configuration export."
        >
          <textarea className="field" name="evidence_ref" rows={2} required />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Type">
            <select className="field" name="evidence_type">
              <option value="">—</option>
              {(refData?.evidence_types ?? []).map((t: string) => (
                <option key={t} value={t}>
                  {label(t)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Supports" hint="Which claim this evidence backs.">
            <select className="field" name="supports">
              <option value="">—</option>
              {['Identified', 'Mitigated', 'Accepted', 'Promoted_To_Risk'].map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Notes">
          <textarea className="field" name="notes" rows={2} />
        </Field>
        <div className="flex justify-end border-t pt-4">
          <button className="btn-primary">Attach</button>
        </div>
      </form>
    </Modal>
  )
}

function AcceptModal({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean
  onClose: () => void
  onSubmit: (body: any) => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Accept locally"
      description="TINV-5: a local acceptance is always time-bound and capped by configuration."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const f = new FormData(e.target as HTMLFormElement)
          onSubmit({
            acceptance_expiry: f.get('acceptance_expiry'),
            acceptance_rationale: f.get('acceptance_rationale'),
          })
        }}
      >
        <Field label="Acceptance expiry">
          <input className="field" type="date" name="acceptance_expiry" required />
        </Field>
        <Field label="Rationale" hint="Required: acceptance is a decision (TINV-10).">
          <textarea className="field" name="acceptance_rationale" rows={3} required />
        </Field>
        <div className="flex justify-end border-t pt-4">
          <button className="btn-primary">Accept</button>
        </div>
      </form>
    </Modal>
  )
}

function ReopenModal({
  open,
  scenario,
  onClose,
  onSubmit,
}: {
  open: boolean
  scenario: any
  onClose: () => void
  onSubmit: (rationale: string) => void
}) {
  const [rationale, setRationale] = useState('')
  useEffect(() => {
    if (open) setRationale('')
  }, [open])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reopen scenario"
      description="Returning a resolved scenario to Identified is a decision like any other, so it carries a reason (TINV-10)."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit(rationale)
        }}
      >
        <p className="rounded-lg border bg-surface-sunken px-3 py-2.5 text-sm text-ink-muted">
          {scenario?.reference}: {scenario?.description}
        </p>
        <Field label="Why is this being reopened?">
          <textarea
            className="field"
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            required
          />
        </Field>
        <div className="flex justify-end border-t pt-4">
          <button className="btn-primary" disabled={!rationale.trim()}>
            Reopen
          </button>
        </div>
      </form>
    </Modal>
  )
}

function PromoteModal({
  open,
  scenario,
  users,
  onClose,
  onSubmit,
}: {
  open: boolean
  scenario: any
  users: any[]
  onClose: () => void
  onSubmit: (body: any) => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Promote to a new risk"
      description="Creates a risk record at Intake, pre-filled from the scenario. If the register already carries this exposure, link to it instead (TINV-8)."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const f = new FormData(e.target as HTMLFormElement)
          onSubmit({
            tier: f.get('tier'),
            risk_owner_id: f.get('risk_owner_id') || null,
            risk_stakeholder_id: f.get('risk_stakeholder_id') || null,
          })
        }}
      >
        <p className="rounded-lg border bg-surface-sunken px-3 py-2.5 text-sm text-ink-muted">
          {scenario?.description}
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
          <button className="btn-primary">Create risk record</button>
        </div>
      </form>
    </Modal>
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
          <button className="btn-primary btn-sm mt-3" disabled={!canSign || busy} onClick={onSign}>
            Sign off
          </button>
        </>
      )}
    </div>
  )
}
