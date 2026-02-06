import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { OrchestrationState } from '../../types/cockpit';

interface OrchestrationPanelProps {
  projectId: string | null;
  runId: string | null;
}

const OrchestrationPanel = ({ projectId, runId }: OrchestrationPanelProps) => {
  const [state, setState] = useState<OrchestrationState | null>(null);
  const [scheme, setScheme] = useState('');
  const [queue, setQueue] = useState('');
  const [finalReview, setFinalReview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId || !runId) {
      setState(null);
      return;
    }

    const load = async () => {
      try {
        const data = await cockpitClient.getOrchestration(projectId, runId);
        setState(data);
        setScheme(data?.scheme || '');
        setQueue(data?.queue?.join('') || '');
        setFinalReview(Boolean(data?.final_review_pending));
      } catch (err) {
        console.error('Failed to load orchestration:', err);
      }
    };

    load();
  }, [projectId, runId]);

  const handleSave = async () => {
    if (!projectId || !runId) return;
    setSaving(true);
    setError(null);
    try {
      const updates: Partial<OrchestrationState> = {
        scheme: scheme.trim() || undefined,
        queue: queue.trim() ? queue.trim().split('') : [],
        final_review_pending: finalReview,
      };
      const next = await cockpitClient.updateOrchestration(projectId, runId, updates);
      setState(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (!projectId || !runId) {
    return (
      <div className="cockpit-orchestration-panel">
        <p className="cockpit-placeholder-text">Select a run to edit orchestration</p>
      </div>
    );
  }

  return (
    <div className="cockpit-orchestration-panel">
      <div className="cockpit-orchestration-header">
        <h3 className="cockpit-subsection-title">Orchestration</h3>
        <button className="cockpit-control-button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
      <label className="cockpit-field-label">Scheme</label>
      <input
        className="cockpit-input"
        value={scheme}
        placeholder="W5R"
        onChange={(e) => setScheme(e.target.value.toUpperCase())}
      />
      <label className="cockpit-field-label">Queue (phase codes)</label>
      <input
        className="cockpit-input"
        value={queue}
        placeholder="R"
        onChange={(e) => setQueue(e.target.value.toUpperCase())}
      />
      <label className="cockpit-control-item">
        <input
          type="checkbox"
          checked={finalReview}
          onChange={(e) => setFinalReview(e.target.checked)}
          className="cockpit-control-checkbox"
        />
        <span className="cockpit-control-label">Final Review Pending</span>
      </label>
      {error && <p className="cockpit-placeholder-text">{error}</p>}
      {state && (
        <p className="cockpit-placeholder-text">
          Current scheme: {state.scheme || 'unset'} · Cursor: {state.cursor ?? '—'}
        </p>
      )}
    </div>
  );
};

export default OrchestrationPanel;
