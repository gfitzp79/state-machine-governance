/** The operating model, read-only.
 *
 * Everything here comes from config/governance.yml as the running API loaded
 * it: appetite bands, acceptance windows, taxonomies, escalation windows, edit
 * permissions. It is shown rather than edited on purpose. Changing appetite or
 * an acceptance window changes how the rules behave for every record, so a
 * change belongs in a reviewed commit to that file (and a restart), not in a
 * form anyone with the right role can submit. An approval-gated editor is a
 * separate piece of work.
 */

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { Card, PageLoader, Tabs } from '../components/ui'
import { label } from '../lib/format'

// Sections in the order a governance reader would look for them. Anything the
// API serves that is not listed here still appears, under "Other".
const SECTIONS: { id: string; title: string; keys: string[]; note?: string }[] = [
  {
    id: 'appetite',
    title: 'Appetite and scoring',
    keys: ['rating_bands', 'ratings', 'review_cadence_days', 'acceptance_rules', 'treatment_strategies'],
    note: 'Band boundaries and appetite positions are configurable. The five rating names, the 1 to 5 scales and the four treatment strategies are fixed, because database constraints name them.',
  },
  {
    id: 'controls',
    title: 'Control effectiveness',
    keys: ['ce_ratings', 'ce_likelihood_reduction', 'ce_expiry_months', 'ce_degradation_sla_days', 'controls'],
  },
  { id: 'taxonomy', title: 'Risk and policy taxonomy', keys: ['risk', 'policy'] },
  { id: 'threat', title: 'Threat and compliance', keys: ['threat', 'compliance'] },
  { id: 'people', title: 'Roles and permissions', keys: ['roles', 'permissions', 'ownership_by_severity', 'seniority_ladder'] },
  { id: 'escalation', title: 'Escalation and treatment', keys: ['escalation', 'treatment'] },
]

function heading(key: string) {
  const text = label(key)
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function isScalar(v: unknown) {
  return v === null || ['string', 'number', 'boolean'].includes(typeof v)
}

function Scalar({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-ink-faint">none</span>
  if (typeof value === 'boolean') return <span>{value ? 'Yes' : 'No'}</span>
  return <span className="tabular-nums">{typeof value === 'string' ? label(value) : String(value)}</span>
}

function Value({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  if (isScalar(value)) return <Scalar value={value} />
  if (Array.isArray(value)) {
    if (value.every(isScalar)) {
      return (
        <div className="flex flex-wrap gap-1">
          {value.length === 0 && <span className="text-ink-faint">none</span>}
          {value.map((v, i) => (
            <span key={i} className="chip">
              <Scalar value={v} />
            </span>
          ))}
        </div>
      )
    }
    const cols = Array.from(new Set(value.flatMap((row) => Object.keys(row ?? {}))))
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="border-b bg-surface-sunken">
            <tr>
              {cols.map((c) => (
                <th key={c} className="table-head whitespace-nowrap">
                  {label(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {value.map((row, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c} className="table-cell align-top">
                    <Value value={(row as any)?.[c]} depth={depth + 1} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  const entries = Object.entries(value as Record<string, unknown>)
  return (
    <dl className="divide-y">
      {entries.map(([k, v]) => (
        <div key={k} className="grid gap-1 py-2 sm:grid-cols-[14rem_1fr] sm:gap-4">
          <dt className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{label(k)}</dt>
          <dd className="min-w-0 text-sm text-ink">
            <Value value={v} depth={depth + 1} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

export default function Settings() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [roles, setRoles] = useState<any>(null)
  const [tab, setTab] = useState('appetite')

  useEffect(() => {
    api.get<Record<string, unknown>>('/config/governance').then(setConfig).catch(() => undefined)
    api.get<any>('/roles').then(setRoles).catch(() => undefined)
  }, [])

  if (!config || !roles) return <PageLoader />

  const merged: Record<string, unknown> = {
    ...config,
    roles: roles.definitions,
    ownership_by_severity: roles.ownership_by_severity,
    seniority_ladder: roles.seniority,
  }
  const placed = new Set(SECTIONS.flatMap((s) => s.keys).concat(['organisation']))
  const other = Object.keys(merged).filter((k) => !placed.has(k))
  const sections = other.length ? [...SECTIONS, { id: 'other', title: 'Other', keys: other }] : SECTIONS
  const current = sections.find((s) => s.id === tab) ?? sections[0]

  return (
    <>
      <PageHeader
        title="Settings"
        description="Your operating model, exactly as the running platform loaded it from config/governance.yml. Read-only here: these values change how the rules behave for every record, so a change is a reviewed edit to that file followed by a restart, not a form."
      />
      <div className="mb-4 rounded-lg border bg-surface-sunken px-4 py-3 text-sm text-ink-muted">
        To change a value, edit <span className="mono">platform/config/governance.yml</span> and run{' '}
        <span className="mono">docker compose restart api</span>. The file is validated at start-up, and the
        API refuses to start on a value it cannot enforce. See the configuration guide in{' '}
        <span className="mono">platform/docs/CONFIGURATION.md</span>.
      </div>
      <Tabs tabs={sections.map((s) => ({ id: s.id, label: s.title }))} active={current.id} onChange={setTab} />
      <div className="mt-4 space-y-4">
        {current.note && <p className="text-sm text-ink-muted">{current.note}</p>}
        {current.keys
          .filter((k) => k in merged)
          .map((k) => (
            <Card key={k} title={heading(k)}>
              <Value value={merged[k]} />
            </Card>
          ))}
      </div>
    </>
  )
}
