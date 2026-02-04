import { useState } from 'react';

interface LaunchPanelProps {
  projectPath: string | null;
  runId: string | null;
}

const LaunchPanel = ({ projectPath, runId }: LaunchPanelProps) => {
  const [driver, setDriver] = useState<string>('claude_code');
  const [gitIsolation, setGitIsolation] = useState<boolean>(true);

  const generateCommand = (): string => {
    if (!runId || !projectPath) return '';

    const parts = [
      'ralph-engine',
      'run',
      `"${projectPath}"`,
      `--run-id "${runId}"`,
      `--driver "${driver}"`,
      '--resume',
    ];

    if (gitIsolation) {
      parts.push('--enforce-git');
    }

    return parts.join(' ');
  };

  const command = generateCommand();

  if (!runId || !projectPath) {
    return (
      <div className="cockpit-launch-panel">
        <p className="cockpit-placeholder-text">Select a run to generate launch command</p>
      </div>
    );
  }

  return (
    <div className="cockpit-launch-panel">
      <h3 className="cockpit-subsection-title">Engine Launch</h3>

      {/* Driver selection */}
      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Driver</label>
        <select
          className="cockpit-select"
          value={driver}
          onChange={(e) => setDriver(e.target.value)}
        >
          <option value="claude_code">Claude Code</option>
          <option value="codex_cli">Codex CLI</option>
          <option value="stub">Stub</option>
          <option value="shell">Shell</option>
        </select>
      </div>

      {/* Git isolation toggle */}
      <div className="cockpit-launch-section">
        <label className="cockpit-control-item">
          <input
            type="checkbox"
            checked={gitIsolation}
            onChange={(e) => setGitIsolation(e.target.checked)}
            className="cockpit-control-checkbox"
          />
          <span className="cockpit-control-label">Enforce Git</span>
        </label>
      </div>

      {/* Generated command */}
      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Command</label>
        <div className="cockpit-command-box">
          <code className="cockpit-command-text">{command}</code>
        </div>
        <button
          className="cockpit-launch-button"
          onClick={() => navigator.clipboard.writeText(command)}
        >
          Copy Command
        </button>
      </div>
    </div>
  );
};

export default LaunchPanel;
