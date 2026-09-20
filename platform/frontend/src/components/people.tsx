/** Owner pickers that offer only people who hold the role.
 *
 * Every owner field listed all fourteen users, so a risk could name the GRC
 * Engineer as its Risk Owner and a policy could be owned by a Control Operator.
 * The roles were configured and the acting user's role gated every transition,
 * but the person the record named as accountable was checked against nothing.
 *
 * `RINV-15` now refuses that on write. This is the other half: the interface
 * stops offering what the write would refuse. Filtering here alone would have
 * been presentation, which is why the rule went in first.
 *
 * Roles match on a prefix, so `role="AppSec"` covers AppSec_Lead and
 * AppSec_Engineer.
 */

import { useEffect, useState } from 'react'
import { api, type User } from '../lib/api'
import { Field } from './ui'

/** One in-flight request per role, shared by every picker asking for it.
 *
 * Three owner fields on one page would otherwise fetch the same list three
 * times. Promises are cached rather than results so simultaneous mounts join
 * the same request instead of racing. */
const cache = new Map<string, Promise<User[]>>()

export function peopleWithRole(role?: string): Promise<User[]> {
  const key = role ?? ''
  if (!cache.has(key)) {
    // Several roles are given comma separated and sent as repeated params,
    // for fields whose rule is a band rather than a single role: policy
    // approval is "CISO or above", which is CISO and Admin.
    const query = role
      ? '/users?' +
        role
          .split(',')
          .map((r) => 'role=' + encodeURIComponent(r.trim()))
          .join('&')
      : '/users'
    cache.set(
      key,
      api.get<User[]>(query).catch((err) => {
        // A failed fetch must not be cached, or the picker stays empty for the
        // rest of the session with no way to retry.
        cache.delete(key)
        throw err
      })
    )
  }
  return cache.get(key)!
}

/** Drop everything, for after roles change in Settings. */
export function forgetPeople() {
  cache.clear()
}

export function usePeople(role?: string): { people: User[]; loading: boolean; failed: boolean } {
  const [people, setPeople] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    setLoading(true)
    setFailed(false)
    peopleWithRole(role)
      .then((rows) => live && setPeople(rows))
      .catch(() => live && setFailed(true))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [role])

  return { people, loading, failed }
}

export function PersonSelect({
  role,
  value,
  onChange,
  name,
  defaultValue,
  label,
  hint,
  placeholder = 'Unassigned',
  disabled,
  exclude,
  excludeReason,
  showSeniority,
}: {
  /** The role the person must hold. Omit to offer everybody, which is only
   *  right for a field that genuinely has no role requirement. */
  role?: string
  value?: string | null
  onChange?: (id: string | null) => void
  /** For the handful of forms that read their values off the DOM on submit
   *  rather than holding them in state. Pass `name` instead of value/onChange. */
  name?: string
  defaultValue?: string
  label: string
  hint?: string
  placeholder?: string
  disabled?: boolean
  /** A person the rules forbid here, such as the Risk Owner in the Stakeholder
   *  field under SEP-1. Shown but not selectable, with the reason, because
   *  hiding them makes the separation rule look like a missing person. */
  exclude?: string | null
  excludeReason?: string
  /** For approval fields, where the constraint is seniority rather than role
   *  (section 2.3 of the codified rules). */
  showSeniority?: boolean
}) {
  const { people, loading, failed } = usePeople(role)

  const empty = !loading && !failed && people.length === 0
  const note = failed
    ? 'Could not load people. The list will fill in when the API is reachable.'
    : empty
      ? 'Nobody holds ' +
        (role ? role.split(',').join(' or ') : 'any role') +
        '. An Admin can grant it under Settings.'
      : hint

  return (
    <Field label={label} hint={note}>
      <select
        className="field"
        name={name}
        {...(name
          ? { defaultValue: defaultValue ?? '' }
          : { value: value ?? '', onChange: (e) => onChange?.(e.target.value || null) })}
        disabled={disabled || loading || empty || failed}
      >
        <option value="">{loading ? 'Loading...' : placeholder}</option>
        {people.map((u) => {
          const blocked = !!exclude && u.id === exclude
          const detail = showSeniority ? u.seniority : u.job_title
          return (
            <option key={u.id} value={u.id} disabled={blocked}>
              {u.full_name}
              {detail ? ', ' + detail : ''}
              {blocked && excludeReason ? ' (' + excludeReason + ')' : ''}
            </option>
          )
        })}
      </select>
    </Field>
  )
}
