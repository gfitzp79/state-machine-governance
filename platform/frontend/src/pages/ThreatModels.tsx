import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Plus, ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { PersonSelect } from '../components/people'
import { Badge, Card, Field, Modal, PageLoader, Table, useToast } from '../components/ui'
import { cx, formatDate, label } from '../lib/format'

export default function ThreatModels() {
  const [rows, setRows] = useState<any[] | null>(null)
  const [assets, setAssets] = useState<any[]>([])
  const [open, setOpen] = useState(false)
  const { push } = useToast()

  const load = () => api.get<any[]>('/threat-models').then(setRows)

  useEffect(() => {
    load().catch(() => undefined)
    api.get<any[]>('/assets').then(setAssets).catch(() => undefined)
  }, [])

  if (!rows) return <PageLoader />

  return (
    <>
      <PageHeader
        title="Threat models"
        description="STRIDE threat models bound bidirectionally to GRC state. A scenario is only Mitigated while the control mitigating it is genuinely operating (TINV-4); when that control fails, the scenario re-opens and the model loses its sign-off."
        actions={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" />
            New threat model
          </button>
        }
      />

      <Card bodyClassName="p-0">
        <Table columns={['Model', 'State', 'Sign-off', 'Scenarios', 'Unresolved', '']}>
          {rows.map((m) => (
            <tr key={m.id} className="group hover:bg-surface-sunken/60">
              <td className="table-cell">
                <Link to={`/threat-models/${m.id}`} className="block">
                  <span className="mono text-ink-faint">{m.reference}</span>
                  <p className="mt-0.5 font-medium text-ink group-hover:text-accent">{m.title}</p>
                  <span className="mt-1 inline-block text-xs text-ink-muted">
                    {m.asset_name} · {m.methodology} · {m.component_count} components
                  </span>
                </Link>
              </td>
              <td className="table-cell">
                <Badge value={m.lifecycle_state} />
              </td>
              <td className="table-cell">
                {m.fully_signed_off ? (
                  <span className="chip border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300">
                    <ShieldCheck className="h-3 w-3" />
                    Dual sign-off
                  </span>
                ) : (
                  <div className="flex gap-1">
                    <span
                      className={cx(
                        'chip',
                        m.appsec_signoff_by
                          ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                          : 'border-line bg-surface-sunken text-ink-faint',
                      )}
                    >
                      AppSec
                    </span>
                    <span
                      className={cx(
                        'chip',
                        m.owner_signoff_by
                          ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300'
                          : 'border-line bg-surface-sunken text-ink-faint',
                      )}
                    >
                      Owner
                    </span>
                  </div>
                )}
              </td>
              <td className="table-cell text-sm">
                <span className="tabular-nums text-ink">{m.scenario_count}</span>
                <span className="text-ink-faint">
                  {' '}
                  · {m.mitigated_count} mitigated · {m.promoted_count} promoted ·{' '}
                  {m.accepted_count} accepted
                </span>
              </td>
              <td className="table-cell">
                {m.unresolved_count > 0 ? (
                  <span className="inline-flex items-center gap-1 text-sm font-semibold text-amber-600 dark:text-amber-400">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {m.unresolved_count}
                  </span>
                ) : (
                  <span className="text-sm text-ink-faint">none</span>
                )}
              </td>
              <td className="table-cell text-right">
                <Link to={`/threat-models/${m.id}`} className="btn-ghost btn-sm">
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
        title="New threat model"
        description="Models start at Scope. They reach Active only with independent AppSec and System Owner sign-off and every scenario resolved."
      >
        <ModelForm
          assets={assets}
          onSubmit={async (body) => {
            try {
              await api.post('/threat-models', body)
              setOpen(false)
              await load()
              push({ kind: 'ok', title: 'Threat model created at Scope' })
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

function ModelForm({
  assets,
  onSubmit,
}: {
  assets: any[]
  onSubmit: (b: any) => void
}) {
  const [form, setForm] = useState<any>({
    title: '',
    attack_surface_id: assets[0]?.id ?? '',
    system_owner_id: '',
    appsec_partner_id: '',
    description: '',
  })
  const set = (k: string, v: string) => setForm((f: any) => ({ ...f, [k]: v }))

  useEffect(() => {
    if (!form.attack_surface_id && assets[0]) set('attack_surface_id', assets[0].id)
  }, [assets])

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
      <Field label="Attack surface">
        <select
          className="field"
          value={form.attack_surface_id}
          onChange={(e) => set('attack_surface_id', e.target.value)}
        >
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({label(a.tier)})
            </option>
          ))}
        </select>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <PersonSelect
          label="System owner"
          role="System_Owner"
          hint="TINV-2: cannot also provide the AppSec signature."
          placeholder="Select"
          value={form.system_owner_id}
          onChange={(id) => set('system_owner_id', id ?? '')}
        />
        <PersonSelect
          label="AppSec partner"
          role="AppSec"
          hint="AppSec_Lead or AppSec_Engineer (TINV-12)."
          value={form.appsec_partner_id}
          onChange={(id) => set('appsec_partner_id', id ?? '')}
        />
      </div>
      <Field label="Description">
        <textarea
          className="field"
          rows={3}
          value={form.description}
          onChange={(e) => set('description', e.target.value)}
        />
      </Field>
      <div className="flex justify-end border-t pt-4">
        <button className="btn-primary" disabled={!form.title.trim() || !form.system_owner_id}>
          Create model
        </button>
      </div>
    </form>
  )
}
