/** Users and roles (codified-rules 2.6).
 *
 * A user here is somebody the platform can hold accountable, not just a login,
 * so the screen is built around what a change would do to the records that name
 * them. Removing a role or deactivating an account is refused while the person
 * is still named on open records (USR-3), and the refusal lists them so the
 * administrator can reassign rather than guess. Deleting is only for an account
 * that has left no trace (USR-5); everyone else is deactivated, which keeps
 * their name on the history they made.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { KeyRound, Search, Trash2, UserCheck, UserPlus, UserX } from 'lucide-react'
import { api, ApiError, getStoredUser, type User } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { forgetPeople } from '../components/people'
import { Badge, Card, Empty, Field, Modal, PageLoader, Table, useToast } from '../components/ui'
import { cx, formatDateTime, label } from '../lib/format'

const MANAGERS = ['Admin', 'CISO']

type RoleDef = { id: string; level: number; description?: string }
type RoleInfo = { roles: string[]; levels: Record<string, number>; seniority: string[]; definitions: RoleDef[] }
type Accountable = {
  kind: string
  id: string
  reference: string | null
  title: string | null
  state: string | null
  field: string
  role: string | null
  path: string
}
type Detail = User & { deactivated_at: string | null; accountable_for?: Accountable[]; deletable?: boolean }

function useIsManager() {
  const me = getStoredUser()
  return !!me && me.roles.some((r) => MANAGERS.includes(r))
}

export default function Users() {
  const [users, setUsers] = useState<Detail[] | null>(null)
  const [roleInfo, setRoleInfo] = useState<RoleInfo | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'active' | 'inactive' | 'all'>('active')
  const [roleFilter, setRoleFilter] = useState('')
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const manager = useIsManager()

  const load = useCallback(() => {
    api.get<Detail[]>('/users?active_only=false').then(setUsers).catch(() => undefined)
  }, [])

  useEffect(() => {
    load()
    api.get<RoleInfo>('/roles').then(setRoleInfo).catch(() => undefined)
  }, [load])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (users ?? []).filter(
      (u) =>
        (status === 'all' || (status === 'active') === u.is_active) &&
        (!roleFilter || u.roles.includes(roleFilter)) &&
        (!q || `${u.full_name} ${u.email} ${u.job_title ?? ''}`.toLowerCase().includes(q)),
    )
  }, [users, query, status, roleFilter])

  if (!users || !roleInfo) return <PageLoader />

  const activeCount = users.filter((u) => u.is_active).length

  return (
    <>
      <PageHeader
        title="Users and roles"
        description="The people the platform holds accountable. A role here is what an owner field checks (ROLE-1), so removing one, or deactivating someone, is refused while they are still named on open records. Reassign first; the refusal lists what to move (USR-3)."
        actions={
          manager ? (
            <button className="btn-primary" onClick={() => setCreating(true)}>
              <UserPlus className="h-4 w-4" />
              New user
            </button>
          ) : undefined
        }
      />

      {!manager && (
        <div className="mb-4 rounded-lg border bg-surface-sunken px-4 py-3 text-sm text-ink-muted">
          You can see who holds which role. Adding, changing and deactivating users needs Admin or CISO (USR-1).
        </div>
      )}

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
          <div className="relative min-w-[14rem] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <input
              id="user-search"
              className="field pl-9"
              placeholder="Search by name, email or job title"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select id="user-status" className="field w-auto" value={status} onChange={(e) => setStatus(e.target.value as any)}>
            <option value="active">Active ({activeCount})</option>
            <option value="inactive">Deactivated ({users.length - activeCount})</option>
            <option value="all">Everyone ({users.length})</option>
          </select>
          <select id="user-role" className="field w-auto" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">Any role</option>
            {roleInfo.roles.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
        </div>
        {filtered.length === 0 ? (
          <Empty title="Nobody matches" hint="Change the search or the filters." />
        ) : (
          <Table columns={['Person', 'Seniority', 'Roles', 'Status', '']}>
            {filtered.map((u) => (
              <tr key={u.id} className={cx(!u.is_active && 'opacity-60')}>
                <td className="table-cell">
                  <p className="font-medium text-ink">{u.full_name}</p>
                  <p className="text-xs text-ink-muted">
                    {u.email}
                    {u.job_title ? ' · ' + u.job_title : ''}
                  </p>
                </td>
                <td className="table-cell whitespace-nowrap text-sm">{label(u.seniority)}</td>
                <td className="table-cell">
                  <div className="flex flex-wrap gap-1">
                    {u.roles.length === 0 && <span className="text-xs text-ink-faint">No roles</span>}
                    {u.roles.map((r) => (
                      <span key={r} className="chip">
                        {label(r)}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="table-cell whitespace-nowrap">
                  <Badge value={u.is_active ? 'Active' : 'Deactivated'} />
                </td>
                <td className="table-cell text-right">
                  <button className="btn-ghost btn-sm" onClick={() => setSelected(u.id)}>
                    {manager ? 'Manage' : 'View'}
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {creating && (
        <CreateUser
          roleInfo={roleInfo}
          onClose={() => setCreating(false)}
          onDone={(id) => {
            setCreating(false)
            forgetPeople()
            load()
            setSelected(id)
          }}
        />
      )}
      {selected && (
        <ManageUser
          key={selected}
          userId={selected}
          roleInfo={roleInfo}
          manager={manager}
          onClose={() => setSelected(null)}
          onChanged={() => {
            forgetPeople()
            load()
          }}
        />
      )}
    </>
  )
}

/* ---------------------------------------------------------------- roles */

function RolePicker({
  roleInfo,
  value,
  onChange,
  disabled,
}: {
  roleInfo: RoleInfo
  value: string[]
  onChange: (roles: string[]) => void
  disabled?: boolean
}) {
  const defs = [...roleInfo.definitions].sort((a, b) => a.level - b.level || a.id.localeCompare(b.id))
  return (
    <fieldset disabled={disabled} className="grid gap-1.5 sm:grid-cols-2">
      {defs.map((d) => {
        const on = value.includes(d.id)
        return (
          <label
            key={d.id}
            className={cx(
              'flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm',
              on ? 'border-accent bg-accent-soft' : 'hover:bg-surface-sunken',
              disabled && 'cursor-not-allowed opacity-70',
            )}
          >
            <input
              id={'role-' + d.id}
              type="checkbox"
              className="mt-0.5"
              checked={on}
              onChange={(e) => onChange(e.target.checked ? [...value, d.id] : value.filter((r) => r !== d.id))}
            />
            <span className="min-w-0">
              <span className="font-medium text-ink">{label(d.id)}</span>
              <span className="ml-1.5 text-[11px] text-ink-faint">level {d.level}</span>
              {d.description && <span className="block text-xs text-ink-muted">{d.description}</span>}
            </span>
          </label>
        )
      })}
    </fieldset>
  )
}

function Refusal({ error }: { error: ApiError | null }) {
  if (!error) return null
  const records = ((error.detail as any)?.records ?? []) as Accountable[]
  const references = ((error.detail as any)?.references ?? []) as string[]
  return (
    <div role="alert" className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
      <p className="font-medium">{error.message}</p>
      {records.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {records.map((r) => (
            <li key={r.kind + r.id + r.field}>
              <Link className="underline" to={r.path}>
                {r.reference ?? label(r.kind)}
              </Link>{' '}
              {r.title} · {label(r.field)}
              {r.state ? ' · ' + label(r.state) : ''}
            </li>
          ))}
        </ul>
      )}
      {references.length > 0 && <p className="mt-2 text-xs">Found in: {references.join(', ')}</p>}
    </div>
  )
}

/* --------------------------------------------------------------- create */

function CreateUser({
  roleInfo,
  onClose,
  onDone,
}: {
  roleInfo: RoleInfo
  onClose: () => void
  onDone: (id: string) => void
}) {
  const { push } = useToast()
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    job_title: '',
    seniority: 'Manager',
    password: '',
    roles: [] as string[],
  })
  const [error, setError] = useState<ApiError | null>(null)
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal open onClose={onClose} wide title="New user" description="Every account is audited from the moment it exists (USR-7).">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault()
          setError(null)
          try {
            const created = await api.post<User>('/users', { ...form, job_title: form.job_title || null })
            push({ kind: 'ok', title: 'User created', body: created.full_name })
            onDone(created.id)
          } catch (err) {
            if (err instanceof ApiError) setError(err)
          }
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name">
            <input id="new-full-name" className="field" required minLength={2} value={form.full_name} onChange={(e) => set('full_name', e.target.value)} />
          </Field>
          <Field label="Email">
            <input id="new-email" className="field" type="email" required value={form.email} onChange={(e) => set('email', e.target.value)} />
          </Field>
          <Field label="Job title">
            <input id="new-job-title" className="field" value={form.job_title} onChange={(e) => set('job_title', e.target.value)} />
          </Field>
          <Field label="Seniority" hint="Drives who may own a risk at each rating and who may approve (§2.3).">
            <select id="new-seniority" className="field" value={form.seniority} onChange={(e) => set('seniority', e.target.value)}>
              {roleInfo.seniority.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Initial password" hint="At least 8 characters. Share it out of band.">
            <input id="new-password" className="field" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={(e) => set('password', e.target.value)} />
          </Field>
        </div>
        <Field label="Roles">
          <RolePicker roleInfo={roleInfo} value={form.roles} onChange={(r) => set('roles', r)} />
        </Field>
        <Refusal error={error} />
        <div className="flex justify-end gap-2 border-t pt-4">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button id="create-user" className="btn-primary">
            Create user
          </button>
        </div>
      </form>
    </Modal>
  )
}

/* --------------------------------------------------------------- manage */

function ManageUser({
  userId,
  roleInfo,
  manager,
  onClose,
  onChanged,
}: {
  userId: string
  roleInfo: RoleInfo
  manager: boolean
  onClose: () => void
  onChanged: () => void
}) {
  const { push } = useToast()
  const me = getStoredUser()
  const [user, setUser] = useState<Detail | null>(null)
  const [form, setForm] = useState({ full_name: '', job_title: '', seniority: '', roles: [] as string[] })
  const [error, setError] = useState<ApiError | null>(null)
  const [reason, setReason] = useState('')
  const [password, setPassword] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const load = useCallback(() => {
    api.get<Detail>('/users/' + userId).then((u) => {
      setUser(u)
      setForm({ full_name: u.full_name, job_title: u.job_title ?? '', seniority: u.seniority, roles: u.roles })
    })
  }, [userId])
  useEffect(load, [load])

  if (!user) return null
  const self = me?.id === user.id
  const editable = manager && user.is_active
  const rolesChanged = [...form.roles].sort().join() !== [...user.roles].sort().join()

  async function act(fn: () => Promise<unknown>, ok: string) {
    setError(null)
    try {
      await fn()
      push({ kind: 'ok', title: ok })
      onChanged()
      load()
    } catch (err) {
      if (err instanceof ApiError) setError(err)
    }
  }

  return (
    <Modal open onClose={onClose} wide title={user.full_name} description={user.email}>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge value={user.is_active ? 'Active' : 'Deactivated'} />
          {user.deactivated_at && <span className="text-xs text-ink-muted">since {formatDateTime(user.deactivated_at)}</span>}
          {self && <span className="chip">This is you</span>}
        </div>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            act(
              () =>
                api.patch('/users/' + user.id, {
                  full_name: form.full_name,
                  job_title: form.job_title || null,
                  seniority: form.seniority,
                  roles: form.roles,
                }),
              'Changes saved',
            )
          }}
        >
          <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-3">
            <Field label="Full name">
              <input id="edit-full-name" className="field" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </Field>
            <Field label="Job title">
              <input id="edit-job-title" className="field" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} />
            </Field>
            <Field label="Seniority">
              <select id="edit-seniority" className="field" value={form.seniority} onChange={(e) => setForm({ ...form, seniority: e.target.value })}>
                {roleInfo.seniority.map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </Field>
          </fieldset>
          <Field
            label="Roles"
            hint={self ? 'Nobody changes their own roles (USR-2). Ask another administrator.' : undefined}
          >
            <RolePicker roleInfo={roleInfo} value={form.roles} onChange={(r) => setForm({ ...form, roles: r })} disabled={!editable || self} />
          </Field>
          {editable && (
            <div className="flex justify-end">
              <button id="save-user" className="btn-primary">
                {rolesChanged ? 'Save changes and roles' : 'Save changes'}
              </button>
            </div>
          )}
        </form>

        <Refusal error={error} />

        {user.accountable_for && (
          <Card
            title="Accountable for"
            subtitle="Open records that name this person. These must be reassigned before they can be deactivated, or lose the role a field requires."
            bodyClassName="p-0"
          >
            {user.accountable_for.length === 0 ? (
              <p className="px-5 py-3 text-sm text-ink-muted">Nothing open names them.</p>
            ) : (
              <ul className="divide-y text-sm">
                {user.accountable_for.map((r) => (
                  <li key={r.kind + r.id + r.field} className="flex flex-wrap items-center gap-2 px-5 py-2">
                    <Link className="mono text-accent hover:underline" to={r.path} onClick={onClose}>
                      {r.reference ?? label(r.kind)}
                    </Link>
                    <span className="min-w-0 flex-1 truncate text-ink">{r.title}</span>
                    <span className="chip">{label(r.field)}</span>
                    {r.state && <Badge value={r.state} />}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}

        {manager && (
          <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-ink">Reset password</p>
              <div className="flex gap-2">
                <input
                  id="reset-password"
                  className="field"
                  type="password"
                  minLength={8}
                  autoComplete="new-password"
                  placeholder="New password, 8 or more characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  id="reset-password-button"
                  className="btn-ghost"
                  disabled={password.length < 8}
                  onClick={() => act(() => api.post('/users/' + user.id + '/password', { password }), 'Password reset').then(() => setPassword(''))}
                >
                  <KeyRound className="h-4 w-4" />
                  Reset
                </button>
              </div>
            </div>

            <div className="space-y-2">
              {user.is_active ? (
                <>
                  <p className="text-sm font-semibold text-ink">Deactivate</p>
                  <div className="flex gap-2">
                    <input
                      id="deactivate-reason"
                      className="field"
                      placeholder={self ? 'You cannot deactivate yourself' : 'Why, e.g. left the organisation'}
                      disabled={self}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <button
                      id="deactivate-button"
                      className="btn-ghost"
                      disabled={self || !reason.trim()}
                      onClick={() => act(() => api.post('/users/' + user.id + '/deactivate', { reason }), 'Account deactivated').then(() => setReason(''))}
                    >
                      <UserX className="h-4 w-4" />
                      Deactivate
                    </button>
                  </div>
                  <p className="text-xs text-ink-faint">Sign-in stops at once, and their name stays on every record they touched (USR-4).</p>
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold text-ink">Reactivate</p>
                  <button id="reactivate-button" className="btn-ghost" onClick={() => act(() => api.post('/users/' + user.id + '/reactivate'), 'Account reactivated')}>
                    <UserCheck className="h-4 w-4" />
                    Reactivate
                  </button>
                </>
              )}
            </div>

            <div className="space-y-2 sm:col-span-2">
              <p className="text-sm font-semibold text-ink">Delete</p>
              {user.deletable ? (
                confirmDelete ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-ink">Delete {user.full_name} permanently?</span>
                    <button
                      id="confirm-delete"
                      className="btn-danger btn-sm"
                      onClick={async () => {
                        setError(null)
                        try {
                          await api.del('/users/' + user.id)
                          push({ kind: 'ok', title: 'User deleted', body: user.full_name })
                          onChanged()
                          onClose()
                        } catch (err) {
                          if (err instanceof ApiError) setError(err)
                        }
                      }}
                    >
                      Delete permanently
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => setConfirmDelete(false)}>
                      Keep
                    </button>
                  </div>
                ) : (
                  <button id="delete-button" className="btn-ghost" onClick={() => setConfirmDelete(true)}>
                    <Trash2 className="h-4 w-4" />
                    Delete account
                  </button>
                )
              ) : (
                <p className="text-xs text-ink-muted">
                  {self
                    ? 'You cannot delete your own account (USR-2).'
                    : 'Not available: this person has acted in the platform or is named on a record, and deleting them would erase who did what. Deactivate instead (USR-5).'}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
