import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';

interface LaunchPanelProps {
  projectPath: string | null;
  projectId: string | null;
  runId: string | null;
}

const LaunchPanel = ({ projectPath, projectId, runId }: LaunchPanelProps) => {
  const [runIdInput, setRunIdInput] = useState<string>('');
  const [launchMode, setLaunchMode] = useState<'resume' | 'new'>('resume');
  const [driverOverride, setDriverOverride] = useState<string>('');
  const [defaultDriver, setDefaultDriver] = useState<string | null>(null);
  const [driverConfigPath, setDriverConfigPath] = useState<string | null>(null);
  const [gitIsolation, setGitIsolation] = useState<boolean>(true);
  const [maxIterations, setMaxIterations] = useState<number>(12);
  const [autoFollow, setAutoFollow] = useState<boolean>(false);
  const knownDrivers = ['claude_code', 'codex_cli', 'stub', 'shell'];
  const effectiveRunId = runIdInput.trim();

  useEffect(() => {
    if (runId) {
      setRunIdInput(runId);
    }
  }, [runId]);

  useEffect(() => {
    if (!projectId) return;
    const loadDriverConfig = async () => {
      try {
        const config = await cockpitClient.getProjectDriverConfig(projectId);
        setDefaultDriver(config.defaultDriver);
        setDriverConfigPath(config.configPath);
      } catch (error) {
        console.error('Failed to load project driver config:', error);
        setDefaultDriver(null);
        setDriverConfigPath(null);
      }
    };
    loadDriverConfig();
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !effectiveRunId) return;
    const load = async () => {
      try {
        const settings = await cockpitClient.getRunSettings(projectId, effectiveRunId);
        if (settings.max_iterations) {
          setMaxIterations(settings.max_iterations);
        }
      } catch (error) {
        console.error('Failed to load run settings:', error);
      }
    };
    load();
  }, [projectId, effectiveRunId]);

  const generateCommand = (quotePaths: boolean = true, quoteArgs: boolean = true): string => {
    if (!effectiveRunId || !projectPath) return '';

    const projectArg = quotePaths ? `"${projectPath}"` : projectPath;
    const runArg = quoteArgs ? `"${effectiveRunId}"` : effectiveRunId;
    const parts = [
      'ralph-engine',
      'run',
      projectArg,
      `--run-id ${runArg}`,
      `--max-iterations ${maxIterations}`,
    ];

    if (launchMode === 'resume') {
      parts.push('--resume');
    }

    if (driverOverride) {
      const driverArg = quoteArgs ? `"${driverOverride}"` : driverOverride;
      parts.push(`--driver ${driverArg}`);
    }

    if (gitIsolation) {
      parts.push('--enforce-git');
    }

    return parts.join(' ');
  };

  const command = generateCommand(true, true);
  const execCommand = generateCommand(true, true);
  const followCommand = projectPath && effectiveRunId
    ? `ralph-engine tail "${projectPath}" --run-id "${effectiveRunId}" --follow`
    : '';
  const followExecCommand = projectPath && effectiveRunId
    ? `ralph-engine tail "${projectPath}" --run-id "${effectiveRunId}" --follow`
    : '';
  const isMissingInputs = !projectPath || !effectiveRunId;
  const launchLabel = launchMode === 'resume' ? 'Resume Run' : 'Start New Run';
  const defaultDriverLabel = defaultDriver ? `Default (${defaultDriver})` : 'Default (engine default)';
  const selectedDriverIsCustom = defaultDriver !== null && !knownDrivers.includes(defaultDriver);

  if (!projectPath) {
    return (
      <div className="cockpit-launch-panel">
        <p className="cockpit-placeholder-text">Select a project to generate launch command</p>
      </div>
    );
  }

  return (
    <div className="cockpit-launch-panel">
      <h3 className="cockpit-subsection-title">Engine Launch</h3>

      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Run ID</label>
        <input
          className="cockpit-input"
          type="text"
          placeholder="2026-02-14__feature-a"
          value={runIdInput}
          onChange={(e) => setRunIdInput(e.target.value)}
        />
      </div>

      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Mode</label>
        <select
          className="cockpit-select"
          value={launchMode}
          onChange={(e) => setLaunchMode(e.target.value as 'resume' | 'new')}
        >
          <option value="resume">Resume Existing Run</option>
          <option value="new">Start New Run</option>
        </select>
      </div>

      {/* Driver selection */}
      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Driver</label>
        <select
          className="cockpit-select"
          value={driverOverride}
          onChange={(e) => setDriverOverride(e.target.value)}
        >
          <option value="">{defaultDriverLabel}</option>
          <option value="claude_code">Claude Code</option>
          <option value="codex_cli">Codex CLI</option>
          <option value="stub">Stub</option>
          <option value="shell">Shell</option>
          {selectedDriverIsCustom && defaultDriver && (
            <option value={defaultDriver}>Configured ({defaultDriver})</option>
          )}
        </select>
        <p className="cockpit-placeholder-text">
          {driverOverride
            ? `Driver override set to "${driverOverride}" (adds --driver).`
            : `Using project default from ${driverConfigPath || 'ralph/config.json'}.`}
        </p>
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

      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Max Iterations (from now)</label>
        <input
          className="cockpit-input"
          type="number"
          min={1}
          value={maxIterations}
          onChange={(e) => setMaxIterations(Number(e.target.value || 1))}
          onBlur={async () => {
            if (projectId && effectiveRunId) {
              await cockpitClient.updateRunSettings(projectId, effectiveRunId, {
                max_iterations: maxIterations,
              });
            }
          }}
        />
      </div>

      {/* Generated command */}
      <div className="cockpit-launch-section">
        <label className="cockpit-field-label">Command</label>
        <div className="cockpit-command-box">
          <code className="cockpit-command-text">{command}</code>
        </div>
        <button
          className="cockpit-launch-button"
          disabled={isMissingInputs}
          onClick={() => navigator.clipboard.writeText(command)}
        >
          Copy Command
        </button>
        <div className="cockpit-launch-actions">
          <button
            className="cockpit-control-button"
            disabled={isMissingInputs}
            onClick={async () => {
              if (!projectId || !effectiveRunId) return;
              await cockpitClient.executeCommand(
                projectId,
                effectiveRunId,
                execCommand,
                'Ralph Run',
                projectPath,
              );
              if (autoFollow && followExecCommand) {
                await cockpitClient.executeCommand(
                  projectId,
                  effectiveRunId,
                  followExecCommand,
                  'Ralph Follow',
                  projectPath,
                );
              }
            }}
          >
            {launchLabel}
          </button>
          <button
            className="cockpit-control-button"
            disabled={isMissingInputs}
            onClick={async () => {
              if (!projectId || !effectiveRunId || !followExecCommand) return;
              await cockpitClient.executeCommand(
                projectId,
                effectiveRunId,
                followExecCommand,
                'Ralph Follow',
                projectPath,
              );
            }}
          >
            Open Follow Window
          </button>
        </div>
        <label className="cockpit-control-item">
          <input
            type="checkbox"
            checked={autoFollow}
            onChange={(e) => setAutoFollow(e.target.checked)}
            className="cockpit-control-checkbox"
          />
          <span className="cockpit-control-label">Auto-open Follow Window</span>
        </label>
      </div>
    </div>
  );
};

export default LaunchPanel;
