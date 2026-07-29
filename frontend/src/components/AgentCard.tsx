import { useState } from 'react';
import type { AgentInfo, StartStopResponse } from '../types';
import StatusBadge from './StatusBadge';
import AgentDetail from './AgentDetail';

interface Props {
  agent: AgentInfo;
  onStart: (id: string) => Promise<StartStopResponse>;
  onStop: (id: string) => Promise<StartStopResponse>;
}

export default function AgentCard({ agent, onStart, onStop }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const isRunning = agent.status === 'running';
  const isStarting = agent.status === 'starting';

  const handleToggle = async () => {
    setBusy(true);
    try {
      if (isRunning) {
        await onStop(agent.id);
      } else {
        await onStart(agent.id);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleOpen = () => {
    if (agent.url) {
      window.open(agent.url, '_blank');
    }
  };

  const uptime = agent.started_at
    ? Math.floor((Date.now() / 1000) - agent.started_at)
    : 0;

  const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1 }}>
          <span style={{ fontSize: '2rem', lineHeight: 1 }}>{agent.icon}</span>
          <div>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>
              {agent.name_zh}
            </h3>
            <p style={{ color: 'var(--lithos-text-soft)', fontSize: '0.8125rem', margin: '4px 0 0' }}>
              {agent.description}
            </p>
          </div>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      {/* Info Row */}
      <div style={{
        display: 'flex', gap: '2rem', marginTop: '0.75rem',
        color: 'var(--lithos-text-soft)', fontSize: '0.8125rem',
      }}>
        {isRunning && agent.port && (
          <span>端口: <code style={{ color: 'var(--lithos-text)', background: 'rgba(255,255,255,0.06)', padding: '1px 6px', borderRadius: 4 }}>{agent.port}</code></span>
        )}
        {isRunning && uptime > 0 && (
          <span>运行时长: {formatUptime(uptime)}</span>
        )}
        {isRunning && agent.pid > 0 && (
          <span>PID: {agent.pid}</span>
        )}
        {agent.status === 'error' && agent.error_message && (
          <span style={{ color: 'var(--lithos-error)' }}>{agent.error_message}</span>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
        <button
          className={isRunning ? 'btn-danger' : 'btn-primary'}
          onClick={handleToggle}
          disabled={busy || isStarting}
        >
          {isStarting ? '⏳ 启动中...' : isRunning ? '⏹ 停止' : '▶ 启动'}
        </button>
        {isRunning && (
          <button className="btn-secondary" onClick={handleOpen}>
            🔗 打开
          </button>
        )}
        <button
          className="btn-ghost"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '收起 ▲' : '详情 ▼'}
        </button>
      </div>

      {/* Expanded Detail */}
      {expanded && (
        <AgentDetail agentId={agent.id} isRunning={isRunning} />
      )}
    </div>
  );
}