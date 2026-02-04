import { useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { DoctorResult } from '../../types/cockpit';

interface DoctorPanelProps {
  projectId: string | null;
  runId: string | null;
}

const DoctorPanel = ({ projectId, runId }: DoctorPanelProps) => {
  const [result, setResult] = useState<DoctorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDoctor = async () => {
    if (!projectId || !runId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await cockpitClient.runDoctor(projectId, runId);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run doctor');
    } finally {
      setLoading(false);
    }
  };

  if (!projectId || !runId) {
    return (
      <div className="cockpit-doctor-panel">
        <p className="cockpit-placeholder-text">Select a run to run doctor</p>
      </div>
    );
  }

  return (
    <div className="cockpit-doctor-panel">
      <div className="cockpit-doctor-header">
        <h3 className="cockpit-subsection-title">Doctor</h3>
        <button className="cockpit-control-button" onClick={handleDoctor} disabled={loading}>
          {loading ? 'Running...' : 'Run Doctor'}
        </button>
      </div>
      {error && <p className="cockpit-placeholder-text">{error}</p>}
      {result && (
        <div className="cockpit-doctor-output">
          <div className="cockpit-doctor-meta">
            <span>Exit Code: {result.exit_code}</span>
            <span className="cockpit-doctor-command">{result.command}</span>
          </div>
          <pre className="cockpit-doc-text">{result.stdout || 'No output from doctor.'}</pre>
          {result.stderr && <pre className="cockpit-doc-text">{result.stderr}</pre>}
        </div>
      )}
    </div>
  );
};

export default DoctorPanel;
