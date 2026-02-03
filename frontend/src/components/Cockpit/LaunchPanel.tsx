import { useState } from 'react';

interface LaunchPanelProps {
  runId: string | null;
}

const LaunchPanel = ({ runId }: LaunchPanelProps) => {
  const [driver, setDriver] = useState<string>('claude-sonnet');
  const [gitIsolation, setGitIsolation] = useState<boolean>(false);

  const generateCommand = (): string => {
    if (!runId) return '';

    const enginePath = 'C:\\projects\\ralph-engine';
    const parts = [
      'python',
      `"${enginePath}\\ralph_engine\\cli.py"`,
      'run',
      `--run-id "${runId}"`,
      `--driver "${driver}"`,
    ];

    if (gitIsolation) {
      parts.push('--git-isolation');
    }

    return parts.join(' ');
  };

  const command = generateCommand();

  if (!runId) {
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
          <option value="claude-sonnet">Claude Sonnet</option>
          <option value="claude-opus">Claude Opus</option>
          <option value="claude-haiku">Claude Haiku</option>
          <option value="openai-gpt4">OpenAI GPT-4</option>
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
          <span className="cockpit-control-label">Git Isolation</span>
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
