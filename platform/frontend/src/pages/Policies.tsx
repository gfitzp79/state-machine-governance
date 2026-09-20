import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Plus } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { PersonSelect } from '../components/people'
import { Badge, Card, Empty, Field, Modal, PageLoader, Table, Tabs, useToast } from '../components/ui'
import { cx, formatDate, label, relativeDays } from '../lib/format'

export default function Policies() {
  const [policies, setPolicies] = useState<any[] | null>(null)
  const [exceptions, setExceptions] = useState<any[]>([])
  const [ref, setRef] = useState<any>(null)
  const [tab, setTab] = useState('policies')
  const [modal, setModal] = useState<'policy' | 'exception' | null>(null)
  const { push } = useToast()

  const load = async () => {
    setPolicies(await api.get<any[]>('/policies'))
    setExceptions(await api.get<any[]>('/exceptions'))
  }

  useEffect(() => {
    load().catch(() => undefined)
    api.get('/policies/reference-data').then(setRef).catch(() => undefined)
  }, [])

  if (!policies) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Policy and standards"
        description="A policy with no linked control has nothing enforcing it, so it cannot go Active (PINV-1). Exceptions are always time-bound (PINV-2), and version history is immutable (PINV-9)."
        actions={
          <>
            <button className="btn-ghost" onClick={() => setModal('exception')}>
              <Plus className="h-4 w-4" />
              Exception
            </button>
            <button className="btn-primary" onClick={() => setModal('policy')}>
              <Plus className="h-4 w-4" />
              New policy
            </button>
          </>
        }
      />

      <div className="mb-5">
        <Tabs
          tabs={[
            { id: 'policies', label: 'Policies', count: policies.length },
            { id: 'exceptions', label: 'Exceptions', count: exceptions.length },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'policies' && (
        <Card bodyClassName="p-0">
          <Table
            columns={['Policy', 'State', 'Version', 'Controls', 'Exceptions', 'Next review', '']}
          >
            {policies.map((p) => (
              <tr key={p.id} className="group hover:bg-surface-sunken/60">
                <td className="table-cell">
                  <Link to={`/policies/${p.id}`} className="block">
                    <span className="mono text-ink-faint">{p.reference}</span>
                    <p className="mt-0.5 font-medium text-ink group-hover:text-accent">
                      {p.title}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(p.compliance_mappings ?? []).map((m: string) => (
                        <span
                          key={m}
                          className="chip border-line bg-surface-sunken text-ink-faint"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </Link>
                </td>
                <td className="table-cell">
                  <Badge value={p.lifecycle_state} />
                </td>
                <td className="table-cell mono text-ink-muted">{p.version}</td>
                <td className="table-cell">
                  <span
                    className={cx(
                      'text-sm tabular-nums',
                      p.control_count === 0 ? 'text-rose-600 dark:text-rose-400' : 'text-ink',
                    )}
                  >
                    {p.control_count}
                  </span>
                  {p.realignment_pending > 0 && (
                    <span className="ml-2 inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                      <AlertTriangle className="h-3 w-3" />
                      {p.realignment_pending} to re-align
                    </span>
                  )}
                </td>
                <td className="table-cell text-sm tabular-nums text-ink-muted">
                  {p.exception_count}
                </td>
                <td className="table-cell whitespace-nowrap text-sm text-ink-muted">
                  {formatDate(p.next_review_date)}
                </td>
                <td className="table-cell text-right">
                  <Link to={`/policies/${p.id}`} className="btn-ghost btn-sm">
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      {tab === 'exceptions' && (
        <Card bodyClassName="p-0">
          {exceptions.length === 0 ? (
            <Empty title="No exceptions raised" />
          ) : (
            <Table
              columns={['Exception', 'State', 'Expiry', 'Compensating controls', 'Promoted', '']}
            >
              {exceptions.map((e) => (
                <tr key={e.id} className="hover:bg-surface-sunken/60">
                  <td className="table-cell">
                    <span className="mono text-ink-faint">{e.reference}</span>
                    <p className="mt-0.5 font-medium text-ink">{e.title}</p>
                  </td>
                  <td className="table-cell">
                    <Badge value={e.lifecycle_state} />
                  </td>
                  <td className="table-cell whitespace-nowrap text-sm">
                    <span className="text-ink">{formatDate(e.expiry_date)}</span>
                    <span
                      className={cx(
                        'ml-2 text-xs',
                        e.overdue
                          ? 'text-rose-600 dark:text-rose-400'
                          : e.expiring_soon
                            ? 'text-amber-600 dark:text-amber-400'
                            : 'text-ink-faint',
                      )}
                    >
                      {relativeDays(e.expiry_date)}
                    </span>
                  </td>
                  <td className="table-cell">
                    {e.has_compensating_controls ? (
                      <span className="chip border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300">
                        recorded
                      </span>
                    ) : (
                      <span
                        className="chip border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300"
                        title="PE-2: escalated for risk promotion assessment"
                      >
                        none (PE-2)
                      </span>
                    )}
                  </td>
                  <td className="table-cell text-sm text-ink-muted">
                    {e.promoted_risk_id ? (
                      <Link to={`/risks/${e.promoted_risk_id}`} className="text-accent">
                        risk record
                      </Link>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="table-cell text-right">
                    <Link to={`/policies/${e.policy_id}`} className="btn-ghost btn-sm">
                      Policy
                    </Link>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      <Modal
        open={modal === 'policy'}
        onClose={() => setModal(null)}
        wide
        title="New policy"
        description="Policies start as Draft. Activation requires CISO approval, an effective date, and at least one linked control."
      >
        <PolicyForm
          refData={ref}
          onSubmit={async (body) => {
            try {
              await api.post('/policies', body)
              setModal(null)
              await load()
              push({ kind: 'ok', title: 'Policy created as Draft' })
            } catch (err) {
              if (err instanceof ApiError)
                push({ kind: 'error', title: 'Refused', body: err.message, rule: err.rule })
            }
          }}
        />
      </Modal>

      <Modal
        open={modal === 'exception'}
        onClose={() => setModal(null)}
        wide
        title="New policy exception"
        description="An exception always carries an expiry (PINV-2). One year maximum; two requires CISO approval (PE-1)."
      >
        <ExceptionForm
          policies={policies}
          onSubmit={async (body) => {
            try {
              await api.post('/exceptions', body)
              setModal(null)
              await load()
              push({ kind: 'ok', title: 'Exception requested' })
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

function PolicyForm({
  refData,
  onSubmit,
}: {
  refData: any
  onSubmit: (body: any) => void
}) {
  const [form, setForm] = useState<any>({
    title: '',
    policy_type: 'Information_Security',
    scope: '',
    purpose: '',
    body: '',
    review_cycle: 'Annual',
    compliance_mappings: [] as string[],
    policy_owner_id: '',
  })
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))
  const annualForced = (form.compliance_mappings as string[]).some((m) =>
    (refData?.annual_audit_frameworks ?? []).includes(m),
  )

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({ ...form, review_cycle: annualForced ? 'Annual' : form.review_cycle })
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
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Type">
          <select
            className="field"
            value={form.policy_type}
            onChange={(e) => set('policy_type', e.target.value)}
          >
            {(refData?.policy_types ?? []).map((t: string) => (
              <option key={t} value={t}>
                {label(t)}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Review cycle"
          hint={
            annualForced
              ? 'Forced to Annual: this policy maps to an annual-audit framework (PINV-4).'
              : undefined
          }
        >
          <select
            className="field"
            value={annualForced ? 'Annual' : form.review_cycle}
            disabled={annualForced}
            onChange={(e) => set('review_cycle', e.target.value)}
          >
            {(refData?.review_cycles ?? ['Annual', 'Biennial']).map((c: string) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Compliance mappings">
        <div className="flex flex-wrap gap-1.5">
          {(refData?.frameworks ?? []).map((f: string) => {
            const on = (form.compliance_mappings as string[]).includes(f)
            return (
              <button
                key={f}
                type="button"
                onClick={() =>
                  set(
                    'compliance_mappings',
                    on
                      ? (form.compliance_mappings as string[]).filter((x) => x !== f)
                      : [...(form.compliance_mappings as string[]), f],
                  )
                }
                className={cx(
                  'chip',
                  on
                    ? 'border-accent bg-accent text-white'
                    : 'border-line bg-surface-sunken text-ink-muted',
                )}
              >
                {f}
              </button>
            )
          })}
        </div>
      </Field>
      <Field label="Scope">
        <input className="field" value={form.scope} onChange={(e) => set('scope', e.target.value)} />
      </Field>
      <Field label="Purpose">
        <input
          className="field"
          value={form.purpose}
          onChange={(e) => set('purpose', e.target.value)}
        />
      </Field>
      <Field label="Body">
        <textarea
          className="field"
          rows={5}
          value={form.body}
          onChange={(e) => set('body', e.target.value)}
        />
      </Field>
      <PersonSelect
        label="Policy owner"
        role="Policy_Owner"
        value={form.policy_owner_id}
        onChange={(id) => set('policy_owner_id', id ?? '')}
      />
      <div className="flex justify-end border-t pt-4">
        <button className="btn-primary" disabled={!form.title.trim()}>
          Create draft
        </button>
      </div>
    </form>
  )
}

function ExceptionForm({ policies, onSubmit }: { policies: any[]; onSubmit: (b: any) => void }) {
  const [form, setForm] = useState<any>({
    policy_id: policies[0]?.id ?? '',
    title: '',
    business_justification: '',
    risk_statement: '',
    compensating_controls: '',
    expiry_date: '',
  })
  const set = (k: string, v: string) => setForm((f: any) => ({ ...f, [k]: v }))
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(form)
      }}
    >
      <Field label="Policy">
        <select
          className="field"
          value={form.policy_id}
          onChange={(e) => set('policy_id', e.target.value)}
        >
          {policies.map((p) => (
            <option key={p.id} value={p.id}>
              {p.reference} — {p.title}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Title">
        <input
          className="field"
          value={form.title}
          onChange={(e) => set('title', e.target.value)}
          required
        />
      </Field>
      <Field label="Business justification">
        <textarea
          className="field"
          rows={3}
          value={form.business_justification}
          onChange={(e) => set('business_justification', e.target.value)}
          required
        />
      </Field>
      <Field
        label="Risk statement"
        hint="What exposure is being carried by granting this exception. Required for approval."
      >
        <textarea
          className="field"
          rows={2}
          value={form.risk_statement}
          onChange={(e) => set('risk_statement', e.target.value)}
        />
      </Field>
      <Field
        label="Compensating controls"
        hint="PE-2: an exception with no compensating controls is escalated for risk register promotion assessment."
      >
        <textarea
          className="field"
          rows={2}
          value={form.compensating_controls}
          onChange={(e) => set('compensating_controls', e.target.value)}
        />
      </Field>
      <Field label="Expiry date" hint="PINV-2: never open-ended.">
        <input
          className="field"
          type="date"
          value={form.expiry_date}
          onChange={(e) => set('expiry_date', e.target.value)}
          required
        />
      </Field>
      <div className="flex justify-end border-t pt-4">
        <button className="btn-primary" disabled={!form.title.trim() || !form.expiry_date}>
          Request exception
        </button>
      </div>
    </form>
  )
}
