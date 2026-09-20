import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, Lock, Plus, Search } from 'lucide-react'
import { api, ApiError, getStoredUser } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { PersonSelect } from '../components/people'
import { Badge, Card, Field, Modal, PageLoader, Table, useToast } from '../components/ui'
import { cx, formatDate, label } from '../lib/format'

interface RiskRow {
  id: string
  reference: string
  title: string
  lifecycle_state: string
  phase: number
  tier: string | null
  inherent_rating: string | null
  residual_rating: string | null
  residual_score_locked: boolean
  reported_score: number | null
  reported_rating: string | null
  appetite: string | null
  treatment_strategy: string | null
  next_review_date: string | null
  sla_status: string
  escalation_flag: boolean
  control_change_flag: string | null
  risk_owner_id: string | null
}

interface RefData {
  tiers: string[]
  tier_detail?: { id: string; label: string; description: string }[]
  intake_sources: string[]
}

const STATES = [
  'Intake',
  'Preconditions',
  'Scoring',
  'Treatment',
  'Readout',
  'Evidence_Residual',
  'Monitoring',
  'Closed',
]

export default function Risks() {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState<RiskRow[] | null>(null)
  const [refData, setRefData] = useState<RefData | null>(null)
  const [users, setUsers] = useState<{ id: string; full_name: string }[]>([])
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const { push } = useToast()

  const state = params.get('state') ?? ''
  const onlyAboveAppetite = params.get('filter') === 'above_appetite'

  const load = () => api.get<RiskRow[]>('/risks').then(setRows)

  useEffect(() => {
    load().catch(() => undefined)
    api.get<RefData>('/risks/reference-data').then(setRefData).catch(() => undefined)
    api.get<{ id: string; full_name: string }[]>('/users').then(setUsers).catch(() => undefined)
  }, [])

  const filtered = useMemo(() => {
    if (!rows) return []
    const q = query.trim().toLowerCase()
    return rows.filter((r) => {
      if (state && r.lifecycle_state !== state) return false
      if (onlyAboveAppetite && r.appetite !== 'Above Appetite') return false
      if (q && !`${r.reference} ${r.title}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [rows, state, onlyAboveAppetite, query])

  if (!rows) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Risk register"
        description="Seven-phase lifecycle with hard gate enforcement. The reported score is the validated residual where one exists, otherwise the inherent score."
        actions={
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            New risk
          </button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            className="field pl-9"
            placeholder="Search risks"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select
          className="field w-auto"
          value={state}
          onChange={(e) => {
            const next = new URLSearchParams(params)
            e.target.value ? next.set('state', e.target.value) : next.delete('state')
            setParams(next)
          }}
        >
          <option value="">All phases</option>
          {STATES.map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
        <button
          className={cx('btn-ghost', onlyAboveAppetite && 'border-accent text-accent')}
          onClick={() => {
            const next = new URLSearchParams(params)
            onlyAboveAppetite ? next.delete('filter') : next.set('filter', 'above_appetite')
            setParams(next)
          }}
        >
          Above appetite only
        </button>
        <span className="ml-auto text-sm text-ink-muted">
          {filtered.length} of {rows.length}
        </span>
      </div>

      <Card bodyClassName="p-0">
        <Table
          columns={[
            'Risk',
            'Phase',
            'Inherent',
            'Residual',
            'Reported',
            'Treatment',
            'Review due',
            '',
          ]}
        >
          {filtered.map((r) => (
            <tr key={r.id} className="group hover:bg-surface-sunken/60">
              <td className="table-cell">
                <Link to={`/risks/${r.id}`} className="block">
                  <span className="mono text-ink-faint">{r.reference}</span>
                  <p className="mt-0.5 max-w-lg font-medium text-ink group-hover:text-accent">
                    {r.title}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {r.tier && (
                      <span className="chip border-line bg-surface-sunken text-ink-faint">
                        {label(r.tier)}
                      </span>
                    )}
                    {r.escalation_flag && (
                      <span className="chip border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300">
                        <AlertTriangle className="h-3 w-3" />
                        Escalated
                      </span>
                    )}
                    {r.control_change_flag && (
                      <span className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300">
                        {label(r.control_change_flag)}
                      </span>
                    )}
                  </div>
                </Link>
              </td>
              <td className="table-cell whitespace-nowrap">
                <Badge value={r.lifecycle_state} />
                <span className="ml-1.5 text-xs tabular-nums text-ink-faint">{r.phase}/7</span>
              </td>
              <td className="table-cell">
                <Badge value={r.inherent_rating} />
              </td>
              <td className="table-cell">
                {r.residual_score_locked ? (
                  <span className="chip border-line bg-surface-sunken text-ink-faint">
                    <Lock className="h-3 w-3" />
                    Locked
                  </span>
                ) : (
                  <Badge value={r.residual_rating} />
                )}
              </td>
              <td className="table-cell whitespace-nowrap">
                <span className="text-base font-semibold tabular-nums text-ink">
                  {r.reported_score ?? '—'}
                </span>
                <span className="ml-1.5 text-xs text-ink-muted">{r.appetite ?? 'Not yet scored'}</span>
              </td>
              <td className="table-cell text-sm text-ink-muted">
                {label(r.treatment_strategy)}
              </td>
              <td className="table-cell whitespace-nowrap text-sm text-ink-muted">
                {formatDate(r.next_review_date)}
                {r.sla_status !== 'On_Track' && (
                  <Badge value={r.sla_status} className="ml-1.5" />
                )}
              </td>
              <td className="table-cell text-right">
                <Link to={`/risks/${r.id}`} className="btn-ghost btn-sm">
                  Open
                </Link>
              </td>
            </tr>
          ))}
        </Table>
        {filtered.length === 0 && (
          <p className="px-5 py-10 text-center text-sm text-ink-muted">
            No risks match these filters.
          </p>
        )}
      </Card>

      <CreateRiskModal
        open={creating}
        onClose={() => setCreating(false)}
        refData={refData}
        users={users}
        onCreated={async () => {
          setCreating(false)
          await load()
          push({ kind: 'ok', title: 'Risk created at Intake' })
        }}
        onError={(e) =>
          push({
            kind: 'error',
            title: 'Could not create the risk',
            body: e.message,
            rule: e.rule,
          })
        }
      />
    </>
  )
}

function CreateRiskModal({
  open,
  onClose,
  refData,
  users,
  onCreated,
  onError,
}: {
  open: boolean
  onClose: () => void
  refData: RefData | null
  users: { id: string; full_name: string }[]
  onCreated: () => void
  onError: (e: ApiError) => void
}) {
  const me = getStoredUser()
  const [form, setForm] = useState({
    title: '',
    cause: '',
    threat_event: '',
    vulnerability: '',
    impact_statement: '',
    intake_source: 'Assessment',
    tier: 'Tier_3',
    risk_analyst_id: me?.id ?? '',
  })
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post('/risks', form)
      onCreated()
    } catch (err) {
      if (err instanceof ApiError) onError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="New risk"
      description="The structured risk statement is the Phase 1 gate. All four parts must be populated before the risk can leave Intake."
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Title">
          <input
            className="field"
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder="Short, specific description of the exposure"
            required
          />
        </Field>

        <div className="rounded-lg border bg-surface-sunken p-4">
          <p className="mb-3 text-xs text-ink-muted">
            <span className="font-medium text-ink">Because</span> [cause]
            <span className="font-medium text-ink"> there is a risk that</span> [threat event]
            <span className="font-medium text-ink"> exploits</span> [vulnerability]
            <span className="font-medium text-ink"> resulting in</span> [impact].
          </p>
          <div className="space-y-3">
            <Field label="Cause">
              <input
                className="field"
                value={form.cause}
                onChange={(e) => set('cause', e.target.value)}
                placeholder="legacy service accounts use shared static credentials"
              />
            </Field>
            <Field label="Threat event">
              <input
                className="field"
                value={form.threat_event}
                onChange={(e) => set('threat_event', e.target.value)}
                placeholder="a credential-phishing campaign succeeds"
              />
            </Field>
            <Field label="Vulnerability">
              <input
                className="field"
                value={form.vulnerability}
                onChange={(e) => set('vulnerability', e.target.value)}
                placeholder="privileged paths accept non-phishing-resistant factors"
              />
            </Field>
            <Field
              label="Impact"
              hint="Must reference business consequence, not technical failure alone."
            >
              <input
                className="field"
                value={form.impact_statement}
                onChange={(e) => set('impact_statement', e.target.value)}
                placeholder="unauthorised payment authorisation and regulatory sanction"
              />
            </Field>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Intake source">
            <select
              className="field"
              value={form.intake_source}
              onChange={(e) => set('intake_source', e.target.value)}
            >
              {(refData?.intake_sources ?? []).map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Risk tier">
            <select
              className="field"
              value={form.tier}
              onChange={(e) => set('tier', e.target.value)}
            >
              {(refData?.tier_detail ?? []).length > 0
                ? refData!.tier_detail!.map((t) => (
                    <option key={t.id} value={t.id} title={t.description}>
                      {label(t.id)} — {t.label}
                    </option>
                  ))
                : (refData?.tiers ?? []).map((t) => (
                    <option key={t} value={t}>
                      {label(t)}
                    </option>
                  ))}
            </select>
          </Field>
          <PersonSelect
            label="Risk analyst"
            role="Risk_Analyst"
            value={form.risk_analyst_id}
            onChange={(id) => set('risk_analyst_id', id ?? '')}
          />
        </div>

        <div className="flex justify-end gap-2 border-t pt-4">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={busy || !form.title.trim()}>
            Create at Intake
          </button>
        </div>
      </form>
    </Modal>
  )
}
