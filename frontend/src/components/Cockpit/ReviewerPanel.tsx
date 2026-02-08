import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';

interface ReviewerPanelProps {
  projectId: string | null;
  runId: string | null;
}

const ReviewerPanel = ({ projectId, runId }: ReviewerPanelProps) => {
  const [results, setResults] = useState<Array<{ iteration: number; result: Record<string, unknown> }>>([]);
  const [loading, setLoading] = useState(false);

  const loadResults = async () => {
    if (!projectId || !runId) return;
    setLoading(true);
    try {
      const data = await cockpitClient.getReviewerResults(projectId, runId);
      setResults(data);
      console.log('[cockpit][reviewer] results', {
        count: data.length,
        iterations: data.map((entry) => entry.iteration),
      });
    } catch (error) {
      console.error('Failed to load reviewer result:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResults();
    const interval = setInterval(loadResults, 6000);
    return () => clearInterval(interval);
  }, [projectId, runId]);

  if (!projectId || !runId) {
    return (
      <div className="cockpit-reviewer-panel">
        <p className="cockpit-placeholder-text">Select a run to view reviewer output</p>
      </div>
    );
  }

  return (
    <div className="cockpit-reviewer-panel">
      <div className="cockpit-reviewer-header">
        <span className="cockpit-field-label">Latest Reviewer Output</span>
        <button className="cockpit-control-button" onClick={loadResults}>
          Refresh
        </button>
      </div>
      <div className="cockpit-reviewer-results">
        {loading && <p className="cockpit-placeholder-text">Loading reviewer outputs...</p>}
        {!loading && results.length === 0 && (
          <p className="cockpit-placeholder-text">No reviewer output found</p>
        )}
        {results.map((entry) => (
          <div key={entry.iteration} className="cockpit-reviewer-result">
            <div className="cockpit-reviewer-iteration">Reviewer Iteration {entry.iteration}</div>
            <div className="cockpit-doc-content">
              <pre className="cockpit-doc-text">
                {entry.result._parse_error
                  ? (entry.result._raw as string)
                  : JSON.stringify(entry.result, null, 2)}
              </pre>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ReviewerPanel;
