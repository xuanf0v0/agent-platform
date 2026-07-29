import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';

export function useLogStream(agentId: string | null) {
  const [logs, setLogs] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (!agentId) return;

    // Disconnect existing
    if (wsRef.current) {
      wsRef.current.close();
    }

    setLogs([]);
    setConnected(false);

    const ws = new WebSocket(api.logStreamUrl(agentId));
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      setLogs((prev) => {
        const next = [...prev, event.data];
        // Keep last 1000 lines
        if (next.length > 1000) return next.slice(next.length - 1000);
        return next;
      });
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
  }, [agentId]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { logs, connected, connect, disconnect };
}