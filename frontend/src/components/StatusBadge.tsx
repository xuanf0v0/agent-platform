import type { AgentInfo } from '../types';

interface Props {
  status: AgentInfo['status'];
  className?: string;
}

const statusStyles: Record<AgentInfo['status'], { bg: string; dot: string; label: string }> = {
  running: {
    bg: 'rgba(34, 197, 94, 0.12)',
    dot: '#22C55E',
    label: '运行中',
  },
  starting: {
    bg: 'rgba(234, 179, 8, 0.12)',
    dot: '#EAB308',
    label: '启动中',
  },
  stopped: {
    bg: 'rgba(255, 255, 255, 0.06)',
    dot: 'rgba(255, 255, 255, 0.3)',
    label: '已停止',
  },
  error: {
    bg: 'rgba(239, 68, 68, 0.12)',
    dot: '#EF4444',
    label: '错误',
  },
};

export default function StatusBadge({ status, className = '' }: Props) {
  const s = statusStyles[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${className}`}
      style={{ background: s.bg, color: s.dot }}
    >
      <span
        className="inline-block w-2 h-2 rounded-full"
        style={{
          background: s.dot,
          animation: status === 'running' ? 'pulse 2s infinite' : status === 'starting' ? 'pulse 1s infinite' : 'none',
        }}
      />
      {s.label}
    </span>
  );
}