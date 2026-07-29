import { useEffect, useRef, useState } from 'react';
import { useLogStream } from '../hooks/useLogStream';

interface Props {
  agentId: string;
  isRunning: boolean;
}

export default function LogViewer({ agentId, isRunning }: Props) {
  const { logs, connected, connect, disconnect } = useLogStream(agentId);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (isRunning) {
      const connectionTimer = window.setTimeout(connect, 50);
      return () => {
        window.clearTimeout(connectionTimer);
        disconnect();
      };
    } else {
      disconnect();
    }
    return () => disconnect();
  }, [isRunning, connect, disconnect]);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50);
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>
          实时日志
          {isRunning && (
            <span style={{ fontSize: '0.75rem', fontWeight: 400, color: connected ? 'var(--lithos-success)' : 'var(--lithos-text-muted)', marginLeft: '0.5rem' }}>
              {connected ? '● 已连接' : '连接中...'}
            </span>
          )}
        </h4>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.75rem', color: 'var(--lithos-text-soft)', display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              style={{ accentColor: 'var(--lithos-cta)' }}
            />
            自动滚动
          </label>
          <span style={{ fontSize: '0.6875rem', color: 'var(--lithos-text-muted)' }}>
            {logs.length} 行
          </span>
        </div>
      </div>

      <div
        ref={containerRef}
        className="terminal"
        onScroll={handleScroll}
        style={{ height: 400, maxHeight: 400 }}
      >
        {logs.length === 0 ? (
          <span style={{ color: 'var(--lithos-text-muted)' }}>
            {isRunning ? '等待日志输出...' : 'Agent 未运行'}
          </span>
        ) : (
          logs.map((line, i) => (
            <div key={i} style={{ lineHeight: 1.6 }}>
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
