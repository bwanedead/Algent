import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { Repo, Run, Story } from '../../types/cockpit';
import ControlPanel from './ControlPanel';
import EventsPanel from './EventsPanel';
import LaunchPanel from './LaunchPanel';

const CockpitPage = () => {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [prdText, setPrdText] = useState<string | null>(null);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load repos on mount
  useEffect(() => {
    const loadRepos = async () => {
      try {
        const repoList = await cockpitClient.listRepos();
        setRepos(repoList);
        if (repoList.length > 0) {
          setSelectedRepoId(repoList[0].id);
        }
      } catch (error) {
        console.error('Failed to load repos:', error);
      } finally {
        setLoading(false);
      }
    };
    loadRepos();
  }, []);

  // Load runs when repo is selected
  useEffect(() => {
    if (!selectedRepoId) return;
    const loadRuns = async () => {
      try {
        const runList = await cockpitClient.listRuns(selectedRepoId);
        setRuns(runList);
        if (runList.length > 0) {
          setSelectedRunId(runList[0].id);
        }
      } catch (error) {
        console.error('Failed to load runs:', error);
      }
    };
    loadRuns();
  }, [selectedRepoId]);

  // Load run artifacts when run is selected
  useEffect(() => {
    if (!selectedRunId) return;
    const loadRunDetails = async () => {
      try {
        const artifacts = await cockpitClient.getRunArtifacts(selectedRunId);
        if (artifacts.prd) {
          setStories(artifacts.prd.stories);
        }
        setPrdText(artifacts.prdText || null);
        setProgressText(artifacts.progressText || null);
      } catch (error) {
        console.error('Failed to load run artifacts:', error);
      }
    };
    loadRunDetails();
  }, [selectedRunId]);

  const selectedRun = runs.find((r) => r.id === selectedRunId);
  const passedCount = stories.filter((s) => s.passes).length;
  const totalCount = stories.length;

  if (loading) {
    return (
      <div className="cockpit-container">
        <p className="cockpit-placeholder-text">Loading cockpit...</p>
      </div>
    );
  }

  return (
    <div className="cockpit-container">
      {/* Sidebar for repo/run selection */}
      <aside className="cockpit-sidebar">
        <div className="cockpit-section-header">
          <span className="cockpit-label">REPOS & RUNS</span>
        </div>
        <div className="cockpit-sidebar-content">
          {/* Repo selector */}
          <div className="cockpit-subsection">
            <label className="cockpit-field-label">Repository</label>
            <select
              className="cockpit-select"
              value={selectedRepoId || ''}
              onChange={(e) => setSelectedRepoId(e.target.value)}
            >
              {repos.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.name}
                </option>
              ))}
            </select>
          </div>

          {/* Run list */}
          <div className="cockpit-subsection">
            <label className="cockpit-field-label">Runs ({runs.length})</label>
            <div className="cockpit-run-list">
              {runs.map((run) => (
                <button
                  key={run.id}
                  className={`cockpit-run-item ${run.id === selectedRunId ? 'active' : ''}`}
                  onClick={() => setSelectedRunId(run.id)}
                >
                  <div className="cockpit-run-id">{run.id}</div>
                  <div className="cockpit-run-status">{run.status}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* Main detail panel for run state and docs */}
      <main className="cockpit-main">
        <div className="cockpit-section-header">
          <span className="cockpit-label">RUN DETAILS</span>
        </div>
        <div className="cockpit-main-content">
          {selectedRun ? (
            <>
              {/* Run state panel */}
              <div className="cockpit-subsection">
                <h3 className="cockpit-subsection-title">Run State</h3>
                <div className="cockpit-field-grid">
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Status</span>
                    <span className="cockpit-field-value">{selectedRun.status}</span>
                  </div>
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Phase</span>
                    <span className="cockpit-field-value">{selectedRun.phase || 'N/A'}</span>
                  </div>
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Iteration</span>
                    <span className="cockpit-field-value">{selectedRun.iteration || 'N/A'}</span>
                  </div>
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Progress</span>
                    <span className="cockpit-field-value">
                      {passedCount}/{totalCount} stories
                    </span>
                  </div>
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Created</span>
                    <span className="cockpit-field-value">
                      {selectedRun.createdAt ? new Date(selectedRun.createdAt).toLocaleString() : 'N/A'}
                    </span>
                  </div>
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Updated</span>
                    <span className="cockpit-field-value">
                      {selectedRun.updatedAt ? new Date(selectedRun.updatedAt).toLocaleString() : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Docs panel - PRD and Progress text */}
              <div className="cockpit-subsection">
                <h3 className="cockpit-subsection-title">Documentation</h3>
                <div className="cockpit-docs-panel">
                  {/* PRD section */}
                  <div className="cockpit-doc-section">
                    <h4 className="cockpit-doc-section-title">PRD</h4>
                    <div className="cockpit-doc-content">
                      {prdText ? (
                        <pre className="cockpit-doc-text">{prdText}</pre>
                      ) : (
                        <p className="cockpit-placeholder-text">No PRD text available</p>
                      )}
                    </div>
                  </div>

                  {/* Progress section */}
                  <div className="cockpit-doc-section">
                    <h4 className="cockpit-doc-section-title">Progress</h4>
                    <div className="cockpit-doc-content">
                      {progressText ? (
                        <pre className="cockpit-doc-text">{progressText}</pre>
                      ) : (
                        <p className="cockpit-placeholder-text">No progress text available</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Story list */}
              <div className="cockpit-subsection">
                <h3 className="cockpit-subsection-title">Stories ({passedCount}/{totalCount})</h3>
                <div className="cockpit-story-list">
                  {stories.map((story) => (
                    <div key={story.id} className="cockpit-story-item">
                      <div className="cockpit-story-header">
                        <span className={`cockpit-story-status ${story.passes ? 'pass' : 'pending'}`}>
                          {story.passes ? '✓' : '○'}
                        </span>
                        <span className="cockpit-story-id">{story.id}</span>
                        <span className="cockpit-story-size">{story.size}</span>
                      </div>
                      <div className="cockpit-story-title">{story.title}</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <p className="cockpit-placeholder-text">No run selected</p>
          )}
        </div>
      </main>

      {/* Control and events area */}
      <aside className="cockpit-controls">
        <div className="cockpit-section-header">
          <span className="cockpit-label">CONTROL & EVENTS</span>
        </div>
        <div className="cockpit-controls-content">
          <ControlPanel runId={selectedRunId} />
          <EventsPanel runId={selectedRunId} />
          <LaunchPanel runId={selectedRunId} />
        </div>
      </aside>
    </div>
  );
};

export default CockpitPage;
