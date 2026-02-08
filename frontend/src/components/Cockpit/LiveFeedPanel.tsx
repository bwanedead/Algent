import { useEffect, useRef, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { LiveFeed } from '../../types/cockpit';

interface LiveFeedPanelProps {
  projectId: string | null;
  runId: string | null;
}

const LiveFeedPanel = ({ projectId, runId }: LiveFeedPanelProps) => {
  const [live, setLive] = useState<LiveFeed | null>(null);
  const [stream, setStream] = useState<'all' | 'stdout' | 'stderr'>('all');
  const [combinedLines, setCombinedLines] = useState<string[]>([]);
  const [newRange, setNewRange] = useState<{ start: number; end: number; lastAt: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoFollow, setAutoFollow] = useState(true);
  const [lineLimit, setLineLimit] = useState(120);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const combinedLengthRef = useRef(0);

  const pastelColorForSource = (sourceLabel: string): string => {
    let hash = 0;
    for (let i = 0; i < sourceLabel.length; i += 1) {
      hash = (hash * 31 + sourceLabel.charCodeAt(i)) >>> 0;
    }
    const hue = hash % 360;
    return `hsl(${hue} 70% 82%)`;
  };

  const loadLive = async () => {
    if (!projectId || !runId) return;
    setLoading(true);
    try {
      const [data, combined] = await Promise.all([
        cockpitClient.getLiveFeed(projectId, runId, lineLimit),
        cockpitClient.getLiveFeedCombined(projectId, runId),
      ]);
      setLive(data);
      const now = Date.now();
      const prevLength = combinedLengthRef.current;
      const nextLength = combined.length;
      if (nextLength > prevLength) {
        setNewRange((current) => {
          if (current && now - current.lastAt < 5000) {
            return { start: current.start, end: nextLength, lastAt: now };
          }
          return { start: prevLength, end: nextLength, lastAt: now };
        });
      }
      combinedLengthRef.current = nextLength;
      setCombinedLines(combined);
      console.log('[cockpit][live]', {
        projectId,
        runId,
        phase: data.phase,
        iteration: data.iteration,
        stdoutLines: data.stdout.length,
        stderrLines: data.stderr.length,
        combinedLines: combined.length,
      });
    } catch (error) {
      console.error('Failed to load live feed:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!projectId || !runId) {
      setLive(null);
      setCombinedLines([]);
      setNewRange(null);
      combinedLengthRef.current = 0;
      return;
    }
    setCombinedLines([]);
    setNewRange(null);
    combinedLengthRef.current = 0;
    loadLive();
    const interval = setInterval(loadLive, 1500);
    return () => clearInterval(interval);
  }, [projectId, runId, lineLimit]);

  useEffect(() => {
    if (!autoFollow || !containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [live, autoFollow, stream]);

  useEffect(() => {
    if (!newRange) return;
    const timer = setTimeout(() => {
      setNewRange((current) =>
        current && current.lastAt === newRange.lastAt ? null : current,
      );
    }, 1400);
    return () => clearTimeout(timer);
  }, [newRange]);

  if (!projectId || !runId) {
    return (
      <div className="cockpit-live-panel">
        <p className="cockpit-placeholder-text">Select a run to view live output</p>
      </div>
    );
  }

  const stdoutLines = live?.stdout ?? [];
  const stderrLines = live?.stderr ?? [];
  const lines =
    stream === 'stdout'
      ? stdoutLines
      : stream === 'stderr'
        ? stderrLines
        : combinedLines;
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
            className={`cockpit-live-tab ${stream === 'all' ? 'active' : ''}`}
            onClick={() => setStream('all')}
          >
            All
          </button>
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
      <div
        className="cockpit-live-body"
        ref={containerRef}
        onWheel={() => setAutoFollow(false)}
        onTouchStart={() => setAutoFollow(false)}
        onScrollCapture={() => setAutoFollow(false)}
      >
        {loading && lines.length === 0 ? (
          <p className="cockpit-placeholder-text">Loading live output...</p>
        ) : lines.length === 0 ? (
          <p className="cockpit-placeholder-text">No live output yet</p>
        ) : (
          <pre className="cockpit-live-text">
            {stream === 'all'
              ? (() => {
                  let sourceLabel = 'source-0';
                  let sourceColor = pastelColorForSource(sourceLabel);
                  return combinedLines.map((line, idx) => {
                    const isBoundary = line.startsWith('--- ');
                    if (isBoundary) {
                      sourceLabel = line;
                      sourceColor = pastelColorForSource(sourceLabel);
                    }
                    const isNew =
                      newRange && idx >= newRange.start && idx < newRange.end;
                    return (
                      <span
                        key={idx}
                        className={`cockpit-live-line ${isBoundary ? 'source-boundary' : 'source-line'} ${isNew ? 'new' : ''}`}
                        style={{ color: sourceColor }}
                      >
                        {line}
                        {'\n'}
                      </span>
                    );
                  });
                })()
              : lines.join('\n')}
          </pre>
        )}
      </div>
    </div>
  );
};

export default LiveFeedPanel;
