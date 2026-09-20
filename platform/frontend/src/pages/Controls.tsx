import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Plus, Search } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { PersonSelect } from '../components/people'
import { Badge, Card, Field, Modal, PageLoader, Table, useToast } from '../components/ui'
import { cx, formatDate, label } from '../lib/format'

interface ObjectiveRow {
  id: string
  reference: string
  title: string
  family: string
  control_type: string
  lifecycle_state: string
  effective_ce: string
  contributes_to_scoring: boolean
  activity_count: number
  deployment_count: number
  failing_deployments: number
  failure_declared_at: string | null
}

export default function Controls() {
  const [rows, setRows] = useState<ObjectiveRow[] | null>(null)
  const [assets, setAssets] = useState<any[]>([])
  const [ref, setRef] = useState<any>(null)
  const [users, setUsers] = useState<any[]>([])
  const [query, setQuery] = useState('')
  const [state, setState] = useState('')
  const [modal, setModal] = useState<'control' | 'asset' | null>(null)
  const { push } = useToast()

  const load = () => api.get<ObjectiveRow[]>('/controls').then(setRows)
  const loadAssets = () => api.get<any[]>('/assets').then(setAssets)

  useEffect(() => {
    load().catch(() => undefined)
    loadAssets().catch(() => undefined)
    api.get('/controls/reference-data').then(setRef).catch(() => undefined)
    api.get<any[]>('/users').then(setUsers).catch(() => undefined)
  }, [])

  const filtered = useMemo(() => {
    if (!rows) return []
    const q = query.trim().toLowerCase()
    return rows.filter(
      (r) =>
        (!state || r.lifecycle_state === state) &&
        (!q || `${r.reference} ${r.title} ${r.family}`.toLowerCase().includes(q)),
    )
  }, [rows, query, state])

  if (!rows) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Control library"
        description="Objectives define what a control must achieve, activities define how, deployments define where. Effectiveness is assessed per deployment because operational reality differs per asset (CE-3)."
        actions={
          <>
            <button className="btn-ghost" onClick={() => setModal('asset')}>
              <Plus className="h-4 w-4" />
              Asset
            </button>
            <button className="btn-primary" onClick={() => setModal('control')}>
              <Plus className="h-4 w-4" />
              New control
            </button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            className="field pl-9"
            placeholder="Search controls"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select className="field w-auto" value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">All states</option>
          {['Design', 'Implementation', 'Operating', 'Failure', 'Redesign', 'Deprecated'].map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ),
          )}
        </select>
        <span className="ml-auto text-sm text-ink-muted">
          {filtered.length} of {rows.length}
        </span>
      </div>

      <Card bodyClassName="p-0">
        <Table
          columns={['Control', 'State', 'Effective CE', 'Deployments', 'Scoring', '']}
        >
          {filtered.map((r) => (
            <tr key={r.id} className="group hover:bg-surface-sunken/60">
              <td className="table-cell">
                <Link to={`/controls/${r.id}`} className="block">
                  <span className="mono text-ink-faint">{r.reference}</span>
                  <p className="mt-0.5 max-w-lg font-medium text-ink group-hover:text-accent">
                    {r.title}
                  </p>
                  <span className="mt-1 inline-block text-xs text-ink-muted">
                    {label(r.family)} · {r.control_type}
                  </span>
                </Link>
              </td>
              <td className="table-cell whitespace-nowrap">
                <Badge value={r.lifecycle_state} />
                {r.lifecycle_state === 'Failure' && (
                  <span className="mt-1 block text-xs text-rose-600 dark:text-rose-400">
                    since {formatDate(r.failure_declared_at)}
                  </span>
                )}
              </td>
              <td className="table-cell">
                <Badge value={r.effective_ce} />
              </td>
              <td className="table-cell whitespace-nowrap text-sm">
                <span className="tabular-nums text-ink">{r.deployment_count}</span>
                <span className="text-ink-faint"> across {r.activity_count} activities</span>
                {r.failing_deployments > 0 && (
                  <span className="ml-2 inline-flex items-center gap-1 text-xs text-rose-600 dark:text-rose-400">
                    <AlertTriangle className="h-3 w-3" />
                    {r.failing_deployments} impaired
                  </span>
                )}
              </td>
              <td className="table-cell">
                <span
                  className={cx(
                    'chip',
                    r.contributes_to_scoring
                      ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                      : 'border-line bg-surface-sunken text-ink-faint',
                  )}
                >
                  {r.contributes_to_scoring ? 'Contributes' : 'Excluded'}
                </span>
              </td>
              <td className="table-cell text-right">
                <Link to={`/controls/${r.id}`} className="btn-ghost btn-sm">
                  Open
                </Link>
              </td>
            </tr>
          ))}
        </Table>
        {filtered.length === 0 && (
          <p className="px-5 py-10 text-center text-sm text-ink-muted">No controls match.</p>
        )}
      </Card>

      <CreateControlModal
        open={modal === 'control'}
        onClose={() => setModal(null)}
        refData={ref}
        users={users}
        onDone={async () => {
          setModal(null)
          await load()
          push({ kind: 'ok', title: 'Control created in Design state' })
        }}
        onError={(e) => push({ kind: 'error', title: 'Refused', body: e.message, rule: e.rule })}
      />

      <CreateAssetModal
        open={modal === 'asset'}
        onClose={() => setModal(null)}
        refData={ref}
        users={users}
        onDone={async () => {
          setModal(null)
          await loadAssets()
          push({ kind: 'ok', title: 'Asset added to the register' })
        }}
        onError={(e) => push({ kind: 'error', title: 'Refused', body: e.message })}
      />
    </>
  )
}

function CreateControlModal({
  open,
  onClose,
  refData,
  users,
  onDone,
  onError,
}: {
  open: boolean
  onClose: () => void
  refData: any
  users: any[]
  onDone: () => void
  onError: (e: ApiError) => void
}) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    family: 'Governance',
    control_type: 'Preventive',
    control_owner_id: '',
  })
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New control objective"
      description="Controls start in Design. They reach Operating only once a deployment is live and its first effectiveness assessment carries evidence."
    >
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault()
          try {
            await api.post('/controls', form)
            onDone()
          } catch (err) {
            if (err instanceof ApiError) onError(err)
          }
        }}
      >
        <Field label="Title">
          <input
            className="field"
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            required
          />
        </Field>
        <Field label="Description">
          <textarea
            className="field"
            rows={3}
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Family">
            <select
              className="field"
              value={form.family}
              onChange={(e) => set('family', e.target.value)}
            >
              {(refData?.families ?? []).map((f: string) => (
                <option key={f} value={f}>
                  {label(f)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Type">
            <select
              className="field"
              value={form.control_type}
              onChange={(e) => set('control_type', e.target.value)}
            >
              {(refData?.types ?? []).map((t: string) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <PersonSelect
          label="Control owner"
          role="Control_Owner"
          hint="SEP-3: a control owner cannot also be the Risk Owner of a risk this control scores."
          value={form.control_owner_id}
          onChange={(id) => set('control_owner_id', id ?? '')}
        />
        <div className="flex justify-end gap-2 border-t pt-4">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={!form.title.trim()}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  )
}

function CreateAssetModal({
  open,
  onClose,
  refData,
  users,
  onDone,
  onError,
}: {
  open: boolean
  onClose: () => void
  refData: any
  users: any[]
  onDone: () => void
  onError: (e: ApiError) => void
}) {
  const [form, setForm] = useState({
    name: '',
    tier: 'Tier_3',
    description: '',
    system_owner_id: '',
  })
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New asset"
      description="Assets are where controls deploy and what threat models scope to."
    >
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault()
          try {
            await api.post('/assets', form)
            onDone()
          } catch (err) {
            if (err instanceof ApiError) onError(err)
          }
        }}
      >
        <Field label="Name">
          <input
            className="field"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            required
          />
        </Field>
        <Field label="Criticality tier">
          <select className="field" value={form.tier} onChange={(e) => set('tier', e.target.value)}>
            {(refData?.asset_tiers ?? ['Tier_1', 'Tier_2', 'Tier_3', 'Tier_4']).map((t: string) => (
              <option key={t} value={t}>
                {label(t)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Description">
          <textarea
            className="field"
            rows={2}
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </Field>
        <PersonSelect
          label="System owner"
          role="System_Owner"
          hint="CINV-14: the named owner has to hold System_Owner."
          value={form.system_owner_id}
          onChange={(id) => set('system_owner_id', id ?? '')}
        />
        <div className="flex justify-end gap-2 border-t pt-4">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={!form.name.trim()}>
            Add asset
          </button>
        </div>
      </form>
    </Modal>
  )
}
