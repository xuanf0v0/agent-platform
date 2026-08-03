/** Shared TypeScript types for the Agent Manager frontend. */

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  icon: string;
  port: number;
  status: 'stopped' | 'starting' | 'running' | 'error';
  pid: number;
  started_at: number;
  error_message: string;
  url: string | null;
}

export interface ConfigField {
  key: string;
  label: string;
  type: 'boolean' | 'string' | 'secret' | 'number' | 'select';
  value: string;
  default: string;
  is_secret: boolean;
  is_masked: boolean;
  options?: string[];
}

export interface LogResponse {
  agent_id: string;
  lines: string[];
  total: number;
}

export interface StartStopResponse {
  id: string;
  status: string;
  pid: number;
  port?: number;
  url?: string | null;
  error_message: string;
}
