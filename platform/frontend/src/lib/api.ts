const TOKEN_KEY = 'smg-token'
const USER_KEY = 'smg-user'

export interface User {
  id: string
  email: string
  full_name: string
  job_title: string | null
  seniority: string
  roles: string[]
  role_level: number
  is_active: boolean
}

/** A refusal from the engine. `rule` carries the invariant or gate that refused,
 *  so the UI can name the rule rather than showing a generic error. */
export class ApiError extends Error {
  status: number
  code: string
  rule?: string
  detail?: unknown

  constructor(status: number, body: Record<string, unknown>) {
    super((body.message as string) ?? 'Request failed')
    this.status = status
    this.code = (body.code as string) ?? 'error'
    this.rule = (body.invariant as string) ?? (body.constraint as string) ?? undefined
    this.detail = body.detail
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function setSession(token: string, user: User) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    /* private mode: session lives for this tab only */
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    /* ignore */
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 204) return undefined as T

  const text = await res.text()
  const parsed = text ? JSON.parse(text) : {}

  if (!res.ok) {
    if (res.status === 403 && getToken()) {
      clearSession()
      window.location.hash = '#/login'
    }
    throw new ApiError(res.status, parsed)
  }
  return parsed as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

export async function login(email: string, password: string) {
  const res = await request<{ token: string; user: User }>('POST', '/auth/login', {
    email,
    password,
  })
  setSession(res.token, res.user)
  return res.user
}
