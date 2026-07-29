import { useAgents } from '../hooks/useAgents';
import AgentCard from './AgentCard';
import StatusBadge from './StatusBadge';

export default function Dashboard() {
  const { agents, loading, error, toggleAgent, refresh } = useAgents();

  const runningCount = agents.filter((a) => a.status === 'running').length;
  const totalCount = agents.length;

  return (
    <div>
      {/* Header */}
      <header style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>
              🤖 Agent Manager
            </h1>
            <p style={{ color: 'var(--lithos-text-soft)', fontSize: '0.875rem', margin: '4px 0 0' }}>
              统一管理 Amazon Listing Agent 服务
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <button className="btn-ghost" onClick={refresh} disabled={loading}>
              {loading ? '刷新中...' : '↻ 刷新状态'}
            </button>
            <span style={{ fontSize: '0.8125rem', color: 'var(--lithos-text-soft)' }}>
              {runningCount}/{totalCount} 运行中
            </span>
            <StatusBadge status={runningCount > 0 ? 'running' : 'stopped'} />
          </div>
        </div>
      </header>

      {/* Error */}
      {error && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: 8,
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            color: 'var(--lithos-error)',
            fontSize: '0.8125rem',
          }}
        >
          ⚠ 连接后端失败: {error}
        </div>
      )}

      {/* Loading */}
      {loading && agents.length === 0 && (
        <div style={{ color: 'var(--lithos-text-soft)', padding: '2rem', textAlign: 'center' }}>
          加载中...
        </div>
      )}

      {/* Agent Cards */}
      <div>
        {agents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            onToggle={toggleAgent}
          />
        ))}
      </div>
    </div>
  );
}
