import { useState } from 'react';
import ConfigEditor from './ConfigEditor';
import LogViewer from './LogViewer';

interface Props {
  agentId: string;
  isRunning: boolean;
}

type Tab = 'config' | 'logs';

export default function AgentDetail({ agentId, isRunning }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('config');

  const tabs: { key: Tab; label: string }[] = [
    { key: 'config', label: '⚙ 配置' },
    { key: 'logs', label: '📋 日志' },
  ];

  return (
    <div style={{ marginTop: '1rem', borderTop: '1px solid var(--lithos-border)', paddingTop: '1rem' }}>
      {/* Tab Bar */}
      <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1rem' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className="btn-ghost"
            style={{
              fontSize: '0.8125rem',
              padding: '0.375rem 0.875rem',
              borderRadius: 8,
              background: activeTab === tab.key ? 'rgba(255,255,255,0.06)' : 'transparent',
              color: activeTab === tab.key ? 'var(--lithos-text)' : 'var(--lithos-text-soft)',
            }}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'config' && <ConfigEditor agentId={agentId} />}
      {activeTab === 'logs' && <LogViewer agentId={agentId} isRunning={isRunning} />}
    </div>
  );
}