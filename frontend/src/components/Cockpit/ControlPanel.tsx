import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { ControlSignals } from '../../types/cockpit';

interface ControlPanelProps {
  runId: string | null;
}

const ControlPanel = ({ runId }: ControlPanelProps) => {
  const [signals, setSignals] = useState<ControlSignals>({
    pause: false,
    stop_soft: false,
    stop_hard: false,
    skip_iteration: false,
    review_now: false,
    review_next: false,
  });
  const [loading, setLoading] = useState(false);

  // Load control signals when runId changes
  useEffect(() => {
    if (!runId) {
      setSignals({
        pause: false,
        stop_soft: false,
        stop_hard: false,
        skip_iteration: false,
        review_now: false,
        review_next: false,
      });
      return;
    }

    const loadSignals = async () => {
      try {
        const currentSignals = await cockpitClient.getControlSignals(runId);
        setSignals(currentSignals);
      } catch (error) {
        console.error('Failed to load control signals:', error);
      }
    };
    loadSignals();
  }, [runId]);

  // Update a toggle (persistent flag)
  const handleToggle = async (key: keyof ControlSignals) => {
    if (!runId) return;

    setLoading(true);
    try {
      const newValue = !signals[key];
      await cockpitClient.updateControlSignals(runId, { [key]: newValue });
      setSignals((prev) => ({ ...prev, [key]: newValue }));
    } catch (error) {
      console.error(`Failed to toggle ${key}:`, error);
    } finally {
      setLoading(false);
    }
  };

  // Trigger a one-shot action
  const handleOneShot = async (key: keyof ControlSignals) => {
    if (!runId) return;

    setLoading(true);
    try {
      // Set to true
      await cockpitClient.updateControlSignals(runId, { [key]: true });
      setSignals((prev) => ({ ...prev, [key]: true }));

      // Simulate consumption after a short delay
      setTimeout(async () => {
        await cockpitClient.updateControlSignals(runId, { [key]: false });
        setSignals((prev) => ({ ...prev, [key]: false }));
      }, 1000);
    } catch (error) {
      console.error(`Failed to trigger ${key}:`, error);
    } finally {
      setLoading(false);
    }
  };

  if (!runId) {
    return (
      <div className="cockpit-control-panel">
        <p className="cockpit-placeholder-text">Select a run to view controls</p>
      </div>
    );
  }

  return (
    <div className="cockpit-control-panel">
      <h3 className="cockpit-subsection-title">Control Signals</h3>

      {/* Toggle controls (persistent flags) */}
      <div className="cockpit-control-section">
        <h4 className="cockpit-control-section-title">Toggles</h4>
        <div className="cockpit-control-group">
          <label className="cockpit-control-item">
            <input
              type="checkbox"
              checked={signals.pause || false}
              onChange={() => handleToggle('pause')}
              disabled={loading}
              className="cockpit-control-checkbox"
            />
            <span className="cockpit-control-label">Pause</span>
          </label>
          <label className="cockpit-control-item">
            <input
              type="checkbox"
              checked={signals.stop_soft || false}
              onChange={() => handleToggle('stop_soft')}
              disabled={loading}
              className="cockpit-control-checkbox"
            />
            <span className="cockpit-control-label">Stop (Soft)</span>
          </label>
          <label className="cockpit-control-item">
            <input
              type="checkbox"
              checked={signals.stop_hard || false}
              onChange={() => handleToggle('stop_hard')}
              disabled={loading}
              className="cockpit-control-checkbox"
            />
            <span className="cockpit-control-label">Stop (Hard)</span>
          </label>
        </div>
      </div>

      {/* One-shot actions */}
      <div className="cockpit-control-section">
        <h4 className="cockpit-control-section-title">Actions</h4>
        <div className="cockpit-control-group">
          <button
            className="cockpit-control-button"
            onClick={() => handleOneShot('skip_iteration')}
            disabled={loading || signals.skip_iteration}
          >
            Skip Iteration {signals.skip_iteration && '(Pending)'}
          </button>
          <button
            className="cockpit-control-button"
            onClick={() => handleOneShot('review_now')}
            disabled={loading || signals.review_now}
          >
            Review Now {signals.review_now && '(Pending)'}
          </button>
          <button
            className="cockpit-control-button"
            onClick={() => handleOneShot('review_next')}
            disabled={loading || signals.review_next}
          >
            Review Next {signals.review_next && '(Pending)'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
