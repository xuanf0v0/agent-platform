import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { AgentInfo, StartStopResponse } from '../types';

export function useAgents() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      setError(null);
      const data = await api.listAgents();
      setAgents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const toggleAgent = useCallback(async (id: string): Promise<StartStopResponse> => {
    const result = await api.toggleAgent(id);
    setAgents((current) => current.map((agent) => (
      agent.id === id
        ? { ...agent, ...result, started_at: result.status === 'running' ? Date.now() / 1000 : 0 }
        : agent
    )) as AgentInfo[]);
    return result;
  }, []);

  return { agents, loading, error, toggleAgent, refresh: fetchAgents };
}
