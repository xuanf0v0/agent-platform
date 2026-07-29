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
    // Poll every 3 seconds for status updates
    const interval = setInterval(fetchAgents, 3000);
    return () => clearInterval(interval);
  }, [fetchAgents]);

  const startAgent = useCallback(async (id: string): Promise<StartStopResponse> => {
    const result = await api.startAgent(id);
    await fetchAgents(); // Refresh immediately
    return result;
  }, [fetchAgents]);

  const stopAgent = useCallback(async (id: string): Promise<StartStopResponse> => {
    const result = await api.stopAgent(id);
    await fetchAgents();
    return result;
  }, [fetchAgents]);

  return { agents, loading, error, startAgent, stopAgent, refresh: fetchAgents };
}