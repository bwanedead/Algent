import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';

interface LaunchPanelProps {
  projectPath: string | null;
  projectId: string | null;
  runId: string | null;
}

const KNOWN_DRIVERS = ['claude_code', 'codex_cli', 'stub', 'shell'];

const LaunchPanel = ({ projectPath, projectId, runId }: LaunchPanelProps) => {
  const [runIdInput, setRunIdInput] = useState<string>('');
  const [launchMode, setLaunchMode] = useState<'resume' | 'new'>('resume');
  const [driverMode, setDriverMode] = useState<'single' | 'split'>('single');
  const [driverOverride, setDriverOverride] = useState<string>('');
  const [workerDriverOverride, setWorkerDriverOverride] = useState<string>('');
  const [reviewerDriverOverride, setReviewerDriverOverride] = useState<string>('');
  const [defaultDriver, setDefaultDriver] = useState<string | null>(null);
  const [defaultWorkerDriver, setDefaultWorkerDriver] = useState<string | null>(null);
  const [defaultReviewerDriver, setDefaultReviewerDriver] = useState<string | null>(null);
  const [driverConfigPath, setDriverConfigPath] = useState<string | null>(null);
  const [driverConfigSource, setDriverConfigSource] = useState<'run' | 'project' | 'default'>('default');
  const [gitIsolation, setGitIsolation] = useState<boolean>(true);
  const [maxIterations, setMaxIterations] = useState<number>(12);
  const [autoFollow, setAutoFollow] = useState<boolean>(false);
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
        const config = effectiveRunId
          ? await cockpitClient.getRunDriverConfig(projectId, effectiveRunId)
          : await cockpitClient.getProjectDriverConfig(projectId);
        setDefaultDriver(config.defaultDriver);
        setDefaultWorkerDriver(config.workerDriver || null);
        setDefaultReviewerDriver(config.reviewerDriver || null);
        setDriverConfigPath(config.configPath);
        setDriverConfigSource(config.source || 'default');
        if (config.workerDriver || config.reviewerDriver) {
          setDriverMode('split');
        } else {
          setDriverMode('single');
        }
      } catch (error) {
        console.error('Failed to load driver config:', error);
        setDefaultDriver(null);
        setDefaultWorkerDriver(null);
        setDefaultReviewerDriver(null);
        setDriverConfigPath(null);
        setDriverConfigSource('default');
      }
    };
    loadDriverConfig();
  }, [projectId, effectiveRunId]);

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

    if (driverMode === 'single') {
      if (driverOverride) {
        const driverArg = quoteArgs ? `"${driverOverride}"` : driverOverride;
        parts.push(`--driver ${driverArg}`);
      }
    } else {
      if (workerDriverOverride) {
        const workerArg = quoteArgs ? `"${workerDriverOverride}"` : workerDriverOverride;
        parts.push(`--worker-driver ${workerArg}`);
      }
      if (reviewerDriverOverride) {
        const reviewerArg = quoteArgs ? `"${reviewerDriverOverride}"` : reviewerDriverOverride;
        parts.push(`--reviewer-driver ${reviewerArg}`);
      }
    }

    if (gitIsolation) {
      parts.push('--enforce-git');
    }

    return parts.join(' ');
  };

  const command = generateCommand(true, true);
  const execCommand = generateCommand(true, true);
  const followExecCommand = projectPath && effectiveRunId
    ? `ralph-engine tail "${projectPath}" --run-id "${effectiveRunId}" --follow`
    : '';
  const isMissingInputs = !projectPath || !effectiveRunId;
  const launchLabel = launchMode === 'resume' ? 'Resume Run' : 'Start New Run';
  const sourceLabel = driverConfigSource === 'run'
    ? `run config (${driverConfigPath || 'ralph/runs/<run_id>/config.json'})`
    : driverConfigSource === 'project'
      ? `project config (${driverConfigPath || 'ralph/config.json'})`
      : 'engine defaults';
  const singleDefaultLabel = defaultDriver
    ? `Default (${defaultDriver})`
    : defaultWorkerDriver || defaultReviewerDriver
      ? 'Default (configured split drivers)'
      : 'Default (engine default)';
  const workerDefaultLabel = defaultWorkerDriver
    ? `Default worker (${defaultWorkerDriver})`
    : defaultDriver
      ? `Default worker (${defaultDriver})`
      : 'Default worker (engine default)';
  const reviewerDefaultLabel = defaultReviewerDriver
    ? `Default reviewer (${defaultReviewerDriver})`
    : defaultDriver
      ? `Default reviewer (${defaultDriver})`
      : 'Default reviewer (engine default)';
  const customDefaultDrivers = [defaultDriver, defaultWorkerDriver, defaultReviewerDriver]
    .filter((driver): driver is string => Boolean(driver && !KNOWN_DRIVERS.includes(driver)));
  const uniqueCustomDefaults = [...new Set(customDefaultDrivers)];

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
        <label className="cockpit-field-label">Driver Mode</label>
        <select
          className="cockpit-select"
          value={driverMode}
          onChange={(e) => setDriverMode(e.target.value as 'single' | 'split')}
        >
          <option value="single">Single Driver (--driver)</option>
          <option value="split">Split Drivers (--worker-driver/--reviewer-driver)</option>
        </select>
        {driverMode === 'single' ? (
          <>
            <label className="cockpit-field-label">Driver Override</label>
            <select
              className="cockpit-select"
              value={driverOverride}
              onChange={(e) => setDriverOverride(e.target.value)}
            >
              <option value="">{singleDefaultLabel}</option>
              <option value="claude_code">Claude Code</option>
              <option value="codex_cli">Codex CLI</option>
              <option value="stub">Stub</option>
              <option value="shell">Shell</option>
              {uniqueCustomDefaults.map((driverName) => (
                <option key={`single-${driverName}`} value={driverName}>
                  Configured ({driverName})
                </option>
              ))}
            </select>
          </>
        ) : (
          <>
            <label className="cockpit-field-label">Worker Driver Override</label>
            <select
              className="cockpit-select"
              value={workerDriverOverride}
              onChange={(e) => setWorkerDriverOverride(e.target.value)}
            >
              <option value="">{workerDefaultLabel}</option>
              <option value="claude_code">Claude Code</option>
              <option value="codex_cli">Codex CLI</option>
              <option value="stub">Stub</option>
              <option value="shell">Shell</option>
              {uniqueCustomDefaults.map((driverName) => (
                <option key={`worker-${driverName}`} value={driverName}>
                  Configured ({driverName})
                </option>
              ))}
            </select>
            <label className="cockpit-field-label">Reviewer Driver Override</label>
            <select
              className="cockpit-select"
              value={reviewerDriverOverride}
              onChange={(e) => setReviewerDriverOverride(e.target.value)}
            >
              <option value="">{reviewerDefaultLabel}</option>
              <option value="claude_code">Claude Code</option>
              <option value="codex_cli">Codex CLI</option>
              <option value="stub">Stub</option>
              <option value="shell">Shell</option>
              {uniqueCustomDefaults.map((driverName) => (
                <option key={`reviewer-${driverName}`} value={driverName}>
                  Configured ({driverName})
                </option>
              ))}
            </select>
          </>
        )}
        <p className="cockpit-placeholder-text">
          {driverMode === 'single'
            ? driverOverride
              ? `Driver override set to "${driverOverride}" (adds --driver).`
              : `Using ${sourceLabel}.`
            : workerDriverOverride || reviewerDriverOverride
              ? `Split overrides active:${workerDriverOverride ? ` worker=${workerDriverOverride}` : ''}${reviewerDriverOverride ? ` reviewer=${reviewerDriverOverride}` : ''}.`
              : `Using split defaults from ${sourceLabel}.`}
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
        <div className="cockpit-command-group">
          <div className="cockpit-command-copy-row">
            <button
              className="cockpit-copy-icon-button"
              aria-label="Copy run command"
              title="Copy command"
              disabled={isMissingInputs}
              onClick={() => navigator.clipboard.writeText(command)}
            >
              ⎘
            </button>
          </div>
          <div className="cockpit-command-box">
            <code className="cockpit-command-text">{command}</code>
          </div>
        </div>
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
