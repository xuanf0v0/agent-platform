import { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { ConfigField } from '../types';

interface Props {
  agentId: string;
}

export default function ConfigEditor({ agentId }: Props) {
  const [fields, setFields] = useState<ConfigField[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getConfig(agentId)
      .then((data) => {
        setFields(data);
        setEdited({});
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [agentId]);

  const handleChange = (key: string, value: string) => {
    setEdited((prev) => ({ ...prev, [key]: value }));
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    if (Object.keys(edited).length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateConfig(agentId, edited);
      setFields(updated);
      setEdited({});
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div style={{ color: 'var(--lithos-text-soft)', padding: '1rem 0' }}>加载配置中...</div>;
  }

  if (error && fields.length === 0) {
    return <div style={{ color: 'var(--lithos-error)', padding: '1rem 0' }}>加载失败: {error}</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>配置管理</h4>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {saveSuccess && (
            <span style={{ color: 'var(--lithos-success)', fontSize: '0.8125rem' }}>✓ 已保存</span>
          )}
          <button
            className="btn-primary"
            style={{ padding: '0.375rem 1rem', fontSize: '0.8125rem' }}
            onClick={handleSave}
            disabled={saving || Object.keys(edited).length === 0}
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ color: 'var(--lithos-error)', fontSize: '0.8125rem', marginBottom: '0.5rem' }}>{error}</div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {fields.map((field) => {
          const currentValue = edited[field.key] !== undefined ? edited[field.key] : field.value;
          const isDirty = edited[field.key] !== undefined;

          return (
            <div
              key={field.key}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.75rem',
                padding: '0.5rem 0.75rem',
                background: isDirty ? 'rgba(232, 112, 42, 0.06)' : 'transparent',
                borderRadius: 8,
                border: isDirty ? '1px solid rgba(232, 112, 42, 0.2)' : '1px solid transparent',
                transition: 'background 0.15s',
              }}
            >
              <label style={{ flex: '0 0 140px', fontSize: '0.8125rem', color: 'var(--lithos-text-soft)' }}>
                {field.label}
              </label>
              <div style={{ flex: 1 }}>
                {field.type === 'boolean' ? (
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={currentValue === 'true' || currentValue === 'True'}
                      onChange={(e) => handleChange(field.key, e.target.checked ? 'true' : 'false')}
                    />
                    <span className="toggle-slider" />
                  </label>
                ) : field.type === 'select' && field.options ? (
                  <select
                    className="select-field"
                    value={currentValue}
                    onChange={(e) => handleChange(field.key, e.target.value)}
                  >
                    {field.options.map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                ) : field.type === 'secret' ? (
                  <input
                    type="password"
                    className="input-field"
                    value={currentValue}
                    onChange={(e) => handleChange(field.key, e.target.value)}
                    placeholder={field.is_masked ? '已设置（点击修改）' : '未设置'}
                    style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}
                  />
                ) : field.type === 'number' ? (
                  <input
                    type="number"
                    className="input-field"
                    value={currentValue}
                    onChange={(e) => handleChange(field.key, e.target.value)}
                  />
                ) : (
                  <input
                    type="text"
                    className="input-field"
                    value={currentValue}
                    onChange={(e) => handleChange(field.key, e.target.value)}
                    style={{ fontFamily: field.key.includes('MODEL') ? 'monospace' : 'inherit', fontSize: field.key.includes('MODEL') ? '0.75rem' : '0.875rem' }}
                  />
                )}
              </div>
              {isDirty && (
                <span style={{ fontSize: '0.6875rem', color: 'var(--lithos-cta)' }}>已修改</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}