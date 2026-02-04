import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { Project, Run, Story } from '../../types/cockpit';
import ControlPanel from './ControlPanel';
import EventsPanel from './EventsPanel';
import DoctorPanel from './DoctorPanel';
import LaunchPanel from './LaunchPanel';
import LiveFeedPanel from './LiveFeedPanel';

const CockpitPage = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [newProjectPath, setNewProjectPath] = useState('');
  const [projectError, setProjectError] = useState<string | null>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [summaryText, setSummaryText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load projects on mount
  useEffect(() => {
    const loadProjects = async () => {
      try {
        const projectList = await cockpitClient.listProjects();
        setProjects(projectList);
        if (projectList.length > 0) {
          setSelectedProjectId(projectList[0].id);
        }
      } catch (error) {
        console.error('Failed to load projects:', error);
      } finally {
        setLoading(false);
      }
    };
    loadProjects();
  }, []);

  // Load runs when repo is selected
  useEffect(() => {
    if (!selectedProjectId) return;
    const loadRuns = async () => {
      try {
        const runList = await cockpitClient.listRuns(selectedProjectId);
        setRuns(runList);
        if (runList.length > 0) {
          setSelectedRunId(runList[0].id);
        }
      } catch (error) {
        console.error('Failed to load runs:', error);
      }
    };
    loadRuns();
  }, [selectedProjectId]);

  // Load run artifacts when run is selected
  useEffect(() => {
    if (!selectedProjectId || !selectedRunId) return;
    const loadRunDetails = async () => {
      try {
        const artifacts = await cockpitClient.getRunArtifacts(selectedProjectId, selectedRunId);
        if (artifacts.prd) {
          setStories(artifacts.prd.stories);
        } else {
          setStories([]);
        }
        setProgressText(artifacts.progressText || null);
        setSummaryText(artifacts.summaryText || null);
      } catch (error) {
        console.error('Failed to load run artifacts:', error);
      }
    };
    loadRunDetails();
  }, [selectedProjectId, selectedRunId]);

  const selectedRun = runs.find((r) => r.id === selectedRunId);
  const passedCount = stories.filter((s) => s.passes).length;
  const totalCount = stories.length;
  const selectedProject = projects.find((project) => project.id === selectedProjectId);

  const handleAddProject = async () => {
    if (!newProjectPath.trim()) return;
    try {
      setProjectError(null);
      const project = await cockpitClient.addProject(newProjectPath.trim());
      setProjects((prev) => [...prev, project]);
      setSelectedProjectId(project.id);
      setNewProjectPath('');
    } catch (error) {
      console.error('Failed to add project:', error);
      setProjectError(error instanceof Error ? error.message : 'Failed to add project');
    }
  };

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
          {/* Project selector */}
          <div className="cockpit-subsection">
            <label className="cockpit-field-label">Project</label>
            <select
              className="cockpit-select"
              value={selectedProjectId || ''}
              onChange={(e) => setSelectedProjectId(e.target.value)}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <div className="cockpit-add-project">
              <input
                type="text"
                className="cockpit-input"
                placeholder="C:\\projects\\my-repo"
                value={newProjectPath}
                onChange={(e) => setNewProjectPath(e.target.value)}
              />
              <button className="cockpit-control-button" onClick={handleAddProject}>
                Add Project
              </button>
              {projectError && <p className="cockpit-placeholder-text">{projectError}</p>}
            </div>
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
                  <div className="cockpit-field">
                    <span className="cockpit-field-label">Project</span>
                    <span className="cockpit-field-value">{selectedProject?.path || 'N/A'}</span>
                  </div>
                </div>
              </div>

              {/* Docs panel - Progress and Summary text */}
              <div className="cockpit-subsection">
                <h3 className="cockpit-subsection-title">Documentation</h3>
                <div className="cockpit-docs-panel">
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

                  {/* Summary section */}
                  <div className="cockpit-doc-section">
                    <h4 className="cockpit-doc-section-title">Summary</h4>
                    <div className="cockpit-doc-content">
                      {summaryText ? (
                        <pre className="cockpit-doc-text">{summaryText}</pre>
                      ) : (
                        <p className="cockpit-placeholder-text">No summary text available</p>
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
          <ControlPanel projectId={selectedProjectId} runId={selectedRunId} />
          <LiveFeedPanel projectId={selectedProjectId} runId={selectedRunId} />
          <EventsPanel projectId={selectedProjectId} runId={selectedRunId} />
          <DoctorPanel projectId={selectedProjectId} runId={selectedRunId} />
          <LaunchPanel projectPath={selectedProject?.path || null} runId={selectedRunId} />
        </div>
      </aside>
    </div>
  );
};

export default CockpitPage;
