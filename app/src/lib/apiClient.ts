import { getAccessToken } from '../features/auth/authService'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined

interface ApiRequestOptions extends RequestInit {
  requiresAuth?: boolean
}

export interface CurrentUserResponse {
  id: string
  email: string
  role: string
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function hasApiBaseUrl(): boolean {
  return Boolean(apiBaseUrl)
}

export async function parseApiErrorMessage(response: Response): Promise<string> {
  const fallback = `API request failed with status ${response.status}.`
  const body = await response.text()

  if (!body) {
    return fallback
  }

  try {
    const parsed = JSON.parse(body) as { detail?: string | Array<{ msg?: string }> }

    if (typeof parsed.detail === 'string') {
      return parsed.detail
    }

    if (Array.isArray(parsed.detail)) {
      const messages = parsed.detail
        .map((entry) => entry.msg)
        .filter((message): message is string => Boolean(message))

      if (messages.length > 0) {
        return messages.join(' ')
      }
    }
  } catch {
    // Fall through to the raw body when the response is not JSON.
  }

  return body
}

async function sendApiRequest(
  path: string,
  options: ApiRequestOptions = {},
): Promise<Response> {
  if (!apiBaseUrl) {
    throw new ApiError('Missing VITE_API_BASE_URL.', 0)
  }

  const { requiresAuth = true, headers, body, ...fetchOptions } = options
  const requestHeaders = new Headers(headers)

  if (body && !(body instanceof FormData) && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json')
  }

  if (requiresAuth) {
    const token = await getAccessToken()

    if (!token) {
      throw new ApiError('Missing access token.', 401)
    }

    requestHeaders.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...fetchOptions,
    body,
    headers: requestHeaders,
  })

  if (!response.ok) {
    const message = await parseApiErrorMessage(response)
    throw new ApiError(message, response.status)
  }

  return response
}

export async function apiRequest<TResponse>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<TResponse> {
  const response = await sendApiRequest(path, options)
  return response.json() as Promise<TResponse>
}

export async function apiRequestText(
  path: string,
  options: ApiRequestOptions = {},
): Promise<string> {
  const response = await sendApiRequest(path, options)
  return response.text()
}

export function apiUrl(path: string): string {
  return `${apiBaseUrl ?? ''}${path}`
}

export async function apiRequestVoid(
  path: string,
  options: ApiRequestOptions = {},
): Promise<void> {
  await sendApiRequest(path, options)
}

export async function getCurrentUser(): Promise<CurrentUserResponse> {
  return apiRequest<CurrentUserResponse>('/me')
}
