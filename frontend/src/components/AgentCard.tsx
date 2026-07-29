import { useRef, useState } from 'react';
import type { AgentInfo, StartStopResponse } from '../types';
import StatusBadge from './StatusBadge';
import AgentDetail from './AgentDetail';

interface Props {
  agent: AgentInfo;
  onToggle: (id: string) => Promise<StartStopResponse>;
}

export default function AgentCard({ agent, onToggle }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const togglePending = useRef(false);

  const isRunning = agent.status === 'running';
  const isStarting = agent.status === 'starting';

  const handleToggle = async () => {
    if (togglePending.current) return;
    togglePending.current = true;
    setBusy(true);
    try {
      await onToggle(agent.id);
    } finally {
      togglePending.current = false;
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
    <article className={`card agent-card ${isRunning ? 'agent-card-running' : ''}`}>
      <div className="agent-card-glow" />
      <div className="agent-card-header">
        <div className="agent-identity">
          <span className="agent-icon">{agent.icon}</span>
          <div>
            <span className="agent-type">AI SERVICE · {agent.id.toUpperCase()}</span>
            <h3>{agent.name_zh}</h3>
          </div>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      <p className="agent-description">{agent.description}</p>

      <div className="agent-stats">
        <div><span>PORT</span><strong>{agent.port || '—'}</strong></div>
        <div><span>UPTIME</span><strong>{isRunning && uptime > 0 ? formatUptime(uptime) : '—'}</strong></div>
        <div><span>PROCESS</span><strong>{isRunning && agent.pid > 0 ? agent.pid : 'OFFLINE'}</strong></div>
        {agent.status === 'error' && agent.error_message && (
          <span className="agent-error">{agent.error_message}</span>
        )}
      </div>

      <div className="agent-actions">
        <button
          className={isRunning ? 'btn-danger' : 'btn-primary'}
          onClick={handleToggle}
          disabled={busy || isStarting}
        >
          {isStarting ? '启动中...' : isRunning ? '停止服务' : '启动服务'}
        </button>
        {isRunning && (
          <button className="btn-secondary" onClick={handleOpen}>
            打开工作台 ↗
          </button>
        )}
        <button
          className="btn-ghost"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '收起详情 ↑' : '配置与日志 ↓'}
        </button>
      </div>

      {expanded && (
        <AgentDetail agentId={agent.id} isRunning={isRunning} />
      )}
    </article>
  );
}
