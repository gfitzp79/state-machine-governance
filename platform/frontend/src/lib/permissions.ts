/** Who may edit each kind of record (codified-rules 2.5, PERM-1).
 *
 * Read from the operating model the API serves, so the interface disables
 * exactly what the API would refuse and changes when config/governance.yml
 * changes. Record payloads also carry `can_edit`, which is authoritative for
 * that record; this hook is for screens with no record yet, such as a create
 * button. */

import { useEffect, useState } from 'react'
import { api, getStoredUser } from './api'

type EditKind = 'risk' | 'control' | 'asset'

let cache: Promise<Record<string, string[]>> | null = null

function editPermissions(): Promise<Record<string, string[]>> {
  if (!cache) {
    cache = api
      .get<any>('/config/governance')
      .then((c) => (c?.permissions?.edit ?? {}) as Record<string, string[]>)
      .catch((err) => {
        cache = null
        throw err
      })
  }
  return cache
}

export function useCanEdit(kind: EditKind, alsoRoles: string[] = []): boolean {
  const [allowed, setAllowed] = useState(false)
  const me = getStoredUser()
  const extra = alsoRoles.join(',')
  useEffect(() => {
    let live = true
    editPermissions()
      .then((p) => {
        const roles = [...(p[kind] ?? []), ...(extra ? extra.split(',') : [])]
        if (live) setAllowed(!!me?.roles.some((r) => roles.includes(r)))
      })
      .catch(() => live && setAllowed(false))
    return () => {
      live = false
    }
  }, [kind, extra, me?.id])
  return allowed
}

export function editRolesHint(kind: EditKind): string {
  return kind === 'risk'
    ? 'Risk content is edited by Risk Analysts (PERM-1).'
    : kind === 'control'
      ? 'Control records are edited by Control Analysts (PERM-1).'
      : 'Assets are edited by their system owner or a Control Analyst (PERM-1).'
}
