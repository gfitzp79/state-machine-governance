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
 *  so the UI can name the rule rather than showing a generic error.
 *
 *  Status 0 means the request never reached the API at all. Every failure path
 *  below produces an ApiError, including that one, because pages discard
 *  anything that is not an ApiError - so a plain network rejection would leave
 *  a spinner turning with nothing to explain it. */
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

  /** True when the API could not be reached or did not answer in a language we
   *  speak. Distinct from a refusal: nothing was decided, so nothing is wrong
   *  with what the user asked for. */
  get isUnreachable(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503
  }
}

const UNREACHABLE = {
  code: 'api_unreachable',
  message:
    'Cannot reach the API. It may still be starting up - check it with ' +
    '`docker compose ps` and retry.',
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

  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    // The API is down, DNS failed, or the browser is offline. fetch rejects
    // rather than resolving, so without this the rejection escapes as a bare
    // TypeError and every caller's `instanceof ApiError` check misses it.
    throw new ApiError(0, UNREACHABLE)
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let parsed: Record<string, unknown>
  try {
    parsed = text ? (JSON.parse(text) as Record<string, unknown>) : {}
  } catch {
    // nginx answers a dead upstream with an HTML error page, not JSON. Parsing
    // it throws, and the throw would otherwise replace a legible 502 with a
    // syntax error about an unexpected '<'.
    throw new ApiError(res.ok ? 0 : res.status, UNREACHABLE)
  }

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
