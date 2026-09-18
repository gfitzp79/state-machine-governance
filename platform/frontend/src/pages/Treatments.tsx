import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Plus } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Badge, Card, Field, Modal, PageLoader, Table, useToast } from '../components/ui'
import { cx, formatDate, label } from '../lib/format'

export default function Treatments() {
  const [rows, setRows] = useState<any[] | null>(null)
  const [users, setUsers] = useState<any[]>([])
  const [ref, setRef] = useState<any>(null)
  const [open, setOpen] = useState(false)
  const { push } = useToast()

  const load = () => api.get<any[]>('/treatments').then(setRows)

  useEffect(() => {
    load().catch(() => undefined)
    api.get<any[]>('/users').then(setUsers).catch(() => undefined)
    api.get('/treatments/reference-data').then(setRef).catch(() => undefined)
  }, [])

  if (!rows) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Treatments"
        description="RINV-12: nothing reaches a governance readout without GRC Engineer feasibility validation and an explicit commitment from the treatment owner. Those are two separate confirmations from two different people."
        actions={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" />
            New treatment
          </button>
        }
      />

      <Card bodyClassName="p-0">
        <Table
          columns={['Treatment', 'State', 'RINV-12', 'Owner', 'Target', 'Check-ins', '']}
        >
          {rows.map((t) => (
            <tr key={t.id} className="group hover:bg-surface-sunken/60">
              <td className="table-cell">
                <Link to={`/treatments/${t.id}`} className="block">
                  <span className="mono text-ink-faint">{t.reference}</span>
                  <p className="mt-0.5 max-w-lg font-medium text-ink group-hover:text-accent">
                    {t.title}
                  </p>
                  <span className="mt-1 inline-block text-xs text-ink-muted">
                    {t.treatment_type}
                    {t.loe ? ` · ${t.loe} effort` : ''}
                  </span>
                </Link>
              </td>
              <td className="table-cell">
                <Badge value={t.lifecycle_state} />
              </td>
              <td className="table-cell">
                <div className="flex gap-1">
                  <span
                    className={cx(
                      'chip',
                      t.grc_eng_validated
                        ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                        : 'border-line bg-surface-sunken text-ink-faint',
                    )}
                    title="GRC Engineer feasibility validation"
                  >
                    GRC
                  </span>
                  <span
                    className={cx(
                      'chip',
                      t.owner_committed
                        ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                        : 'border-line bg-surface-sunken text-ink-faint',
                    )}
                    title="Treatment owner commitment"
                  >
                    Owner
                  </span>
                </div>
              </td>
              <td className="table-cell text-sm text-ink-muted">
                {users.find((u) => u.id === t.treatment_owner_id)?.full_name ?? '—'}
              </td>
              <td className="table-cell whitespace-nowrap text-sm">
                <span className={t.overdue ? 'text-rose-600 dark:text-rose-400' : 'text-ink-muted'}>
                  {formatDate(t.target_date)}
                </span>
                {t.overdue && (
                  <AlertTriangle className="ml-1.5 inline h-3.5 w-3.5 text-rose-500" />
                )}
              </td>
              <td className="table-cell text-sm tabular-nums text-ink-muted">
                {t.checkin_count}
              </td>
              <td className="table-cell text-right">
                <Link to={`/treatments/${t.id}`} className="btn-ghost btn-sm">
                  Open
                </Link>
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        wide
        title="New treatment"
        description="Treatments start as Proposed. They cannot be approved until a GRC Engineer validates feasibility and the named owner commits."
      >
        <TreatmentForm
          users={users}
          refData={ref}
          onSubmit={async (body) => {
            try {
              await api.post('/treatments', body)
              setOpen(false)
              await load()
              push({ kind: 'ok', title: 'Treatment created as Proposed' })
            } catch (err) {
              if (err instanceof ApiError)
                push({ kind: 'error', title: 'Refused', body: err.message, rule: err.rule })
            }
          }}
        />
      </Modal>
    </>
  )
}

function TreatmentForm({
  users,
  refData,
  onSubmit,
}: {
  users: any[]
  refData: any
  onSubmit: (b: any) => void
}) {
  const [form, setForm] = useState<any>({
    title: '',
    description: '',
    treatment_type: 'Mitigate',
    treatment_owner_id: '',
    target_date: '',
    loe: 'M',
    check_in_frequency: 'Monthly',
    expected_impact_delta: 0,
    expected_likelihood_delta: -1,
  })
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(form)
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
        <Field label="Type">
          <select
            className="field"
            value={form.treatment_type}
            onChange={(e) => set('treatment_type', e.target.value)}
          >
            {(refData?.types ?? ['Mitigate']).map((t: string) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Treatment owner"
          hint="SEP-2: cannot be the Risk Owner of a risk this treats."
        >
          <select
            className="field"
            value={form.treatment_owner_id}
            onChange={(e) => set('treatment_owner_id', e.target.value)}
          >
            <option value="">Unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} — {u.job_title}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Target date">
          <input
            className="field"
            type="date"
            value={form.target_date}
            onChange={(e) => set('target_date', e.target.value)}
          />
        </Field>
        <Field label="Level of effort">
          <select className="field" value={form.loe} onChange={(e) => set('loe', e.target.value)}>
            {(refData?.loe_bands ?? ['M']).map((l: string) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Check-in frequency">
          <select
            className="field"
            value={form.check_in_frequency}
            onChange={(e) => set('check_in_frequency', e.target.value)}
          >
            {(refData?.checkin_frequencies ?? ['Monthly']).map((f: string) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Expected impact reduction"
          hint="Controls reduce likelihood, not impact (IMP-4). Only a blast-radius change justifies an impact delta."
        >
          <select
            className="field"
            value={form.expected_impact_delta}
            onChange={(e) => set('expected_impact_delta', Number(e.target.value))}
          >
            {[0, -1, -2, -3, -4].map((d) => (
              <option key={d} value={d}>
                {d === 0 ? 'No change' : `${d} level${d === -1 ? '' : 's'}`}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Expected likelihood reduction">
          <select
            className="field"
            value={form.expected_likelihood_delta}
            onChange={(e) => set('expected_likelihood_delta', Number(e.target.value))}
          >
            {[0, -1, -2, -3, -4].map((d) => (
              <option key={d} value={d}>
                {d === 0 ? 'No change' : `${d} level${d === -1 ? '' : 's'}`}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="flex justify-end border-t pt-4">
        <button className="btn-primary" disabled={!form.title.trim()}>
          Create treatment
        </button>
      </div>
    </form>
  )
}
