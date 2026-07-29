import type { AgentInfo, ConfigField, LogResponse, StartStopResponse } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  /** List all agents with status */
  listAgents: () => request<AgentInfo[]>('/api/agents'),

  /** Get single agent status */
  getAgent: (id: string) => request<AgentInfo>(`/api/agents/${id}`),

  /** Start an agent */
  startAgent: (id: string) =>
    request<StartStopResponse>(`/api/agents/${id}/start`, { method: 'POST' }),

  /** Stop an agent */
  stopAgent: (id: string) =>
    request<StartStopResponse>(`/api/agents/${id}/stop`, { method: 'POST' }),

  /** Get agent config */
  getConfig: (id: string) => request<ConfigField[]>(`/api/agents/${id}/config`),

  /** Update agent config */
  updateConfig: (id: string, updates: Record<string, string>) =>
    request<ConfigField[]>(`/api/agents/${id}/config`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),

  /** Get recent logs */
  getLogs: (id: string, lines = 200) =>
    request<LogResponse>(`/api/agents/${id}/logs?lines=${lines}`),

  /** WebSocket URL for live log streaming */
  logStreamUrl: (id: string) => `ws://localhost:8000/ws/agents/${id}/logs`,
};