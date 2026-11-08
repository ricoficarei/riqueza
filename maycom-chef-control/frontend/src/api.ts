import type { Asset, Capabilities, GenerationSettings, Job, LocalEngineSettings } from './types'

let accessToken = ''
export const setAccessToken = (token: string) => { accessToken = token }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError' }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(url, { credentials: 'same-origin', ...init, headers })
  if (!response.ok) {
    let message = `Não foi possível concluir a solicitação (${response.status}).`
    try {
      const data = await response.json()
      const detail = data.detail ?? data.error ?? data.message
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail)) message = detail.map((item: { msg?: string }) => item.msg ?? 'Campo inválido').join('. ')
    } catch { /* The HTTP status remains available when a response has no JSON. */ }
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  capabilities: () => request<Capabilities>('/api/capabilities'),
  localSettings: () => request<LocalEngineSettings>('/api/local/settings'),
  saveLocalSettings: (settings: Pick<LocalEngineSettings, 'url'>) => request<LocalEngineSettings>('/api/local/settings', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }),
  login: (token: string) => request<{ authenticated: boolean }>('/api/session', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }),
  logout: () => request<void>('/api/session/logout', { method: 'POST' }),
  jobs: () => request<Job[] | { jobs: Job[] }>('/api/jobs').then(data => Array.isArray(data) ? data : data.jobs),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  upload: (file: File, role: Asset['role']) => {
    const body = new FormData(); body.append('file', file); body.append('role', role)
    return request<Asset>('/api/assets', { method: 'POST', body })
  },
  deleteAsset: (id: string) => request<void>(`/api/assets/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  reviewAsset: (id: string, token: string, decision: 'approved' | 'rejected') => request<Asset>(`/api/assets/${encodeURIComponent(id)}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Review-Token': token },
    body: JSON.stringify({ decision, fictional_adult_confirmed: decision === 'approved', non_intimate_confirmed: decision === 'approved' }),
  }),
  assets: () => request<Asset[]>('/api/assets'),
  createJob: (character_id: string, reference_id: string, settings: GenerationSettings) => request<Job>('/api/jobs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ character_id, reference_id, settings, rights_confirmed: true, fictional_adult_confirmed: true, non_intimate_confirmed: true }),
  }),
  cancelJob: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  deleteJob: (id: string) => request<void>(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}

export const assetUrl = (asset: Asset) => asset.file_url ?? `/api/assets/${encodeURIComponent(asset.id)}/file`
export const outputUrl = (job: Job) => job.output_url ?? job.result_url ?? null
export const isComplete = (job: Job) => job.status === 'completed'
export const isActive = (job: Job) => ['queued', 'preparing', 'submitting', 'running', 'validating'].includes(job.status)
