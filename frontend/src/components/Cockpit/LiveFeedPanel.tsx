import { useEffect, useRef, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { LiveFeed } from '../../types/cockpit';

interface LiveFeedPanelProps {
  projectId: string | null;
  runId: string | null;
}

const LiveFeedPanel = ({ projectId, runId }: LiveFeedPanelProps) => {
  const [live, setLive] = useState<LiveFeed | null>(null);
  const [stream, setStream] = useState<'stdout' | 'stderr'>('stdout');
  const [loading, setLoading] = useState(false);
  const [autoFollow, setAutoFollow] = useState(true);
  const [lineLimit, setLineLimit] = useState(120);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const loadLive = async () => {
    if (!projectId || !runId) return;
    setLoading(true);
    try {
      const data = await cockpitClient.getLiveFeed(projectId, runId, lineLimit);
      setLive(data);
    } catch (error) {
      console.error('Failed to load live feed:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!projectId || !runId) {
      setLive(null);
      return;
    }
    loadLive();
    const interval = setInterval(loadLive, 1500);
    return () => clearInterval(interval);
  }, [projectId, runId, lineLimit]);

  useEffect(() => {
    if (!autoFollow || !containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [live, autoFollow, stream]);

  if (!projectId || !runId) {
    return (
      <div className="cockpit-live-panel">
        <p className="cockpit-placeholder-text">Select a run to view live output</p>
      </div>
    );
  }

  const lines = stream === 'stdout' ? live?.stdout ?? [] : live?.stderr ?? [];
  const statusLabel =
    live?.phase && live?.iteration !== null
      ? `${live.phase} • iter ${live.iteration}`
      : 'Idle';

  return (
    <div className="cockpit-live-panel">
      <div className="cockpit-live-header">
        <h3 className="cockpit-subsection-title">Live Feed</h3>
        <div className="cockpit-live-status">{statusLabel}</div>
      </div>
      <div className="cockpit-live-controls">
        <div className="cockpit-live-tabs">
          <button
            className={`cockpit-live-tab ${stream === 'stdout' ? 'active' : ''}`}
            onClick={() => setStream('stdout')}
          >
            Stdout
          </button>
          <button
            className={`cockpit-live-tab ${stream === 'stderr' ? 'active' : ''}`}
            onClick={() => setStream('stderr')}
          >
            Stderr
          </button>
        </div>
        <div className="cockpit-live-options">
          <label className="cockpit-events-toggle">
            <input
              type="checkbox"
              checked={autoFollow}
              onChange={(e) => setAutoFollow(e.target.checked)}
              className="cockpit-control-checkbox"
            />
            <span className="cockpit-events-toggle-label">Follow</span>
          </label>
          <select
            className="cockpit-select cockpit-live-select"
            value={lineLimit}
            onChange={(e) => setLineLimit(Number(e.target.value))}
          >
            <option value={80}>80 lines</option>
            <option value={120}>120 lines</option>
            <option value={200}>200 lines</option>
            <option value={400}>400 lines</option>
          </select>
        </div>
      </div>
      <div className="cockpit-live-body" ref={containerRef}>
        {loading && lines.length === 0 ? (
          <p className="cockpit-placeholder-text">Loading live output...</p>
        ) : lines.length === 0 ? (
          <p className="cockpit-placeholder-text">No live output yet</p>
        ) : (
          <pre className="cockpit-live-text">{lines.join('\n')}</pre>
        )}
      </div>
    </div>
  );
};

export default LiveFeedPanel;
