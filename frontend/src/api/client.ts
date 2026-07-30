import type { AgentInfo, ConfigField, LogResponse, StartStopResponse } from '../types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.error || body.detail || `HTTP ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function readSse(
  response: Response,
  onEvent: (event: string, data: any, id?: string) => void,
) {
  if (!response.ok || !response.body) throw new Error(`Stream failed: HTTP ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      if (!block || block.startsWith(':')) continue
      let event = 'message'; let id: string | undefined; const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('id:')) id = line.slice(3).trim()
        if (line.startsWith('data:')) data.push(line.slice(5).trim())
      }
      if (data.length) onEvent(event, JSON.parse(data.join('\n')), id)
    }
    if (done) break
  }
}

const service = (agent: string, path: string) => `/api/agents/${agent}/service/${path}`

export const api = {
  listAgents: () => request<AgentInfo[]>('/api/agents'),
  getAgent: (id: string) => request<AgentInfo>(`/api/agents/${id}`),
  startAgent: (id: string) => request<StartStopResponse>(`/api/agents/${id}/start`, { method: 'POST' }),
  stopAgent: (id: string) => request<StartStopResponse>(`/api/agents/${id}/stop`, { method: 'POST' }),
  getConfig: (id: string) => request<ConfigField[]>(`/api/agents/${id}/config`),
  updateConfig: (id: string, body: Record<string, string>) => request<ConfigField[]>(`/api/agents/${id}/config`, { method: 'PUT', body: JSON.stringify(body) }),
  getLogs: (id: string) => request<LogResponse>(`/api/agents/${id}/logs?lines=200`),
  service: <T>(agent: string, path: string, options?: RequestInit) => request<T>(service(agent, path), options),
  serviceUrl: service,
}
