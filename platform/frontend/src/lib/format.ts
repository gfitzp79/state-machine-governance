export const RATINGS = ['Low', 'Moderate-Low', 'Moderate', 'High', 'Critical'] as const
export type Rating = (typeof RATINGS)[number]

/** Rating colours. Deliberately not a red-to-green gradient: the distinction that
 *  matters is above-appetite versus within-appetite, not a smooth ramp. */
export const ratingTone: Record<string, string> = {
  Critical:
    'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300',
  High: 'border-orange-300 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/60 dark:text-orange-300',
  Moderate:
    'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300',
  'Moderate-Low':
    'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-300',
  Low: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300',
}

export const ratingFill: Record<string, string> = {
  Critical: 'bg-rose-500',
  High: 'bg-orange-500',
  Moderate: 'bg-amber-500',
  'Moderate-Low': 'bg-sky-500',
  Low: 'bg-emerald-500',
}

const NEUTRAL =
  'border-line bg-surface-sunken text-ink-muted'
const GOOD =
  'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300'
const WARN =
  'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300'
const BAD =
  'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300'
const INFO =
  'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-300'

export const stateTone: Record<string, string> = {
  // risk
  Intake: NEUTRAL,
  Preconditions: NEUTRAL,
  Scoring: INFO,
  Treatment: INFO,
  Readout: INFO,
  Evidence_Residual: WARN,
  Monitoring: GOOD,
  Closed: NEUTRAL,
  // control objective / activity / deployment
  Design: NEUTRAL,
  Implementation: INFO,
  Operating: GOOD,
  Failure: BAD,
  Redesign: WARN,
  Deprecated: NEUTRAL,
  Draft: NEUTRAL,
  Active: GOOD,
  Suspended: WARN,
  Retired: NEUTRAL,
  Planned: NEUTRAL,
  Degraded: WARN,
  Failed: BAD,
  Decommissioned: NEUTRAL,
  // policy
  Under_Review: INFO,
  Approved: INFO,
  Under_Revision: WARN,
  Requested: NEUTRAL,
  Rejected: BAD,
  Expired: BAD,
  // treatment
  Proposed: NEUTRAL,
  Validated: INFO,
  In_Progress: INFO,
  Complete: GOOD,
  Cancelled: NEUTRAL,
  // threat model
  Scope: NEUTRAL,
  Decomposition: NEUTRAL,
  Threat_Analysis: INFO,
  Mitigation_Design: INFO,
  Review: WARN,
  Abandoned: NEUTRAL,
  // scenario
  Identified: WARN,
  Mitigated: GOOD,
  Accepted: INFO,
  Promoted_To_Risk: INFO,
  // ce
  'CE-High': GOOD,
  'CE-Medium': INFO,
  'CE-Low': WARN,
  'CE-Unvalidated': NEUTRAL,
  // sla
  On_Track: GOOD,
  At_Risk: WARN,
  Breached: BAD,
  // tests
  Pass: GOOD,
  Partial: WARN,
  Fail: BAD,
  Not_Tested: NEUTRAL,
  // severities
  Medium: WARN,
}

export function tone(value: string | null | undefined): string {
  if (!value) return NEUTRAL
  return stateTone[value] ?? ratingTone[value] ?? NEUTRAL
}

export function label(value: string | null | undefined): string {
  if (!value) return '—'
  return value.replace(/_/g, ' ')
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function relativeDays(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const days = Math.round((d.getTime() - Date.now()) / 86_400_000)
  if (days === 0) return 'today'
  if (days > 0) return `in ${days} day${days === 1 ? '' : 's'}`
  return `${Math.abs(days)} day${days === -1 ? '' : 's'} ago`
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
