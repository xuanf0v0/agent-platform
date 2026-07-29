import { useAgents } from '../hooks/useAgents';
import AgentCard from './AgentCard';
import StatusBadge from './StatusBadge';

export default function Dashboard() {
  const { agents, loading, error, toggleAgent, refresh } = useAgents();

  const runningCount = agents.filter((a) => a.status === 'running').length;
  const totalCount = agents.length;
  const stoppedCount = agents.filter((a) => a.status === 'stopped').length;

  return (
    <div className="dashboard">
      <header className="dashboard-header glass-panel">
        <div className="brand-lockup">
          <div className="brand-mark">A</div>
          <div>
            <div className="eyebrow">AMAZON INTELLIGENCE PLATFORM</div>
            <h1>Agent Control Center</h1>
            <p>统一管理 Listing 智能体、运行状态与服务配置</p>
          </div>
        </div>
        <div className="header-actions">
            <button className="btn-ghost" onClick={refresh} disabled={loading}>
              {loading ? '同步中...' : '↻ 同步状态'}
            </button>
            <StatusBadge status={runningCount > 0 ? 'running' : 'stopped'} />
        </div>
      </header>

      <section className="metrics-grid" aria-label="运行概览">
        <div className="metric-card glass-panel">
          <span className="metric-label">智能体总数</span>
          <strong>{totalCount.toString().padStart(2, '0')}</strong>
          <span className="metric-foot">REGISTERED AGENTS</span>
        </div>
        <div className="metric-card glass-panel metric-active">
          <span className="metric-label">正在运行</span>
          <strong>{runningCount.toString().padStart(2, '0')}</strong>
          <span className="metric-foot"><i /> SYSTEM ACTIVE</span>
        </div>
        <div className="metric-card glass-panel">
          <span className="metric-label">已停止</span>
          <strong>{stoppedCount.toString().padStart(2, '0')}</strong>
          <span className="metric-foot">AVAILABLE CAPACITY</span>
        </div>
        <div className="metric-card glass-panel system-health">
          <span className="metric-label">控制服务</span>
          <strong>ONLINE</strong>
          <span className="metric-foot">LOCAL · PORT 8000</span>
        </div>
      </section>

      {/* Error */}
      {error && (
        <div className="error-banner">
          ⚠ 连接后端失败: {error}
        </div>
      )}

      {/* Loading */}
      {loading && agents.length === 0 && (
        <div className="loading-state glass-panel">
          <span className="loading-orbit" /> 正在连接 Agent 控制服务
        </div>
      )}

      <div className="section-heading">
        <div>
          <span className="eyebrow">DEPLOYMENT WORKSPACE</span>
          <h2>智能体服务</h2>
        </div>
        <span>{totalCount} 个可用服务</span>
      </div>

      <div className="agent-grid">
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
