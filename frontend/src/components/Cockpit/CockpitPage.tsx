import { useEffect, useMemo, useRef, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { Project, Run, Story } from '../../types/cockpit';
import ControlPanel from './ControlPanel';
import EventsPanel from './EventsPanel';
import DoctorPanel from './DoctorPanel';
import LaunchPanel from './LaunchPanel';
import LiveFeedPanel from './LiveFeedPanel';
import TimelinePanel from './TimelinePanel';

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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [infoTab, setInfoTab] = useState<'live' | 'stories' | 'progress' | 'summary'>('live');
  const [timelineOpen, setTimelineOpen] = useState(true);
  const [timelinePos, setTimelinePos] = useState({ x: 0, y: 0 });
  const [timelineDragging, setTimelineDragging] = useState(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });
  const timelineRef = useRef<HTMLDivElement | null>(null);

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
  const runPhase = selectedRun?.phase || 'N/A';
  const runIteration = selectedRun?.iteration ?? 'N/A';
  const runStatus = selectedRun?.status || 'unknown';
  const runUpdated = selectedRun?.updatedAt
    ? new Date(selectedRun.updatedAt).toLocaleString()
    : 'N/A';
  const progressSummary = useMemo(
    () => `${passedCount}/${totalCount || '—'} stories`,
    [passedCount, totalCount],
  );

  useEffect(() => {
    if (!timelineDragging) return;
    const handleMove = (event: MouseEvent) => {
      if (!timelineRef.current) return;
      const overlayRect = timelineRef.current.getBoundingClientRect();
      const nextX = event.clientX - dragOffsetRef.current.x;
      const nextY = event.clientY - dragOffsetRef.current.y;
      const maxX = Math.max(0, window.innerWidth - overlayRect.width);
      const maxY = Math.max(0, window.innerHeight - overlayRect.height);
      setTimelinePos({
        x: Math.min(Math.max(0, nextX), maxX),
        y: Math.min(Math.max(0, nextY), maxY),
      });
    };
    const handleUp = () => setTimelineDragging(false);
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [timelineDragging]);

  const handleTimelineDragStart = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    dragOffsetRef.current = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
    event.preventDefault();
    setTimelineDragging(true);
  };

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
    <div className={`cockpit-container ${sidebarOpen ? 'sidebar-open' : 'sidebar-collapsed'}`}>
      {/* Sidebar for repo/run selection */}
      <aside className="cockpit-sidebar">
        <div className="cockpit-section-header">
          <span className="cockpit-label">PROJECTS</span>
          <button
            className="cockpit-icon-button"
            onClick={() => setSidebarOpen((prev) => !prev)}
            aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarOpen ? '⟨' : '⟩'}
          </button>
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

      {/* Main detail panel for timeline and run state */}
      <main className="cockpit-main">
        <div className="cockpit-section-header">
          <div className="cockpit-header-left">
            <span className="cockpit-label">RUN OVERVIEW</span>
            <button
              className="cockpit-header-button"
              onClick={() => {
                setTimelineOpen((prev) => {
                  const next = !prev;
                  if (next) {
                    setTimelinePos({ x: 0, y: 0 });
                  }
                  return next;
                });
              }}
            >
              {timelineOpen ? 'Hide Timeline' : 'Show Timeline'}
            </button>
          </div>
          <div className="cockpit-run-chipbar">
            <span className="cockpit-chip">{runStatus}</span>
            <span className="cockpit-chip">Phase: {runPhase}</span>
            <span className="cockpit-chip">Iter: {runIteration}</span>
            <span className="cockpit-chip">{progressSummary}</span>
            <span className="cockpit-chip">Updated: {runUpdated}</span>
          </div>
        </div>
        <div className="cockpit-main-content">
          {selectedRun ? (
            <>
              <div className="cockpit-main-grid">
                <div className="cockpit-main-right">
                  <div className="cockpit-subsection">
                    <div className="cockpit-tabs">
                      <button
                        className={`cockpit-tab ${infoTab === 'live' ? 'active' : ''}`}
                        onClick={() => setInfoTab('live')}
                      >
                        Live
                      </button>
                      <button
                        className={`cockpit-tab ${infoTab === 'stories' ? 'active' : ''}`}
                        onClick={() => setInfoTab('stories')}
                      >
                        Stories
                      </button>
                      <button
                        className={`cockpit-tab ${infoTab === 'progress' ? 'active' : ''}`}
                        onClick={() => setInfoTab('progress')}
                      >
                        Progress
                      </button>
                      <button
                        className={`cockpit-tab ${infoTab === 'summary' ? 'active' : ''}`}
                        onClick={() => setInfoTab('summary')}
                      >
                        Summary
                      </button>
                    </div>
                    {infoTab === 'live' && (
                      <LiveFeedPanel projectId={selectedProjectId} runId={selectedRunId} />
                    )}
                    {infoTab === 'stories' && (
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
                    )}
                    {infoTab === 'progress' && (
                      <div className="cockpit-doc-content">
                        {progressText ? (
                          <pre className="cockpit-doc-text">{progressText}</pre>
                        ) : (
                          <p className="cockpit-placeholder-text">No progress text available</p>
                        )}
                      </div>
                    )}
                    {infoTab === 'summary' && (
                      <div className="cockpit-doc-content">
                        {summaryText ? (
                          <pre className="cockpit-doc-text">{summaryText}</pre>
                        ) : (
                          <p className="cockpit-placeholder-text">No summary text available</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
              {timelineOpen && (
                <div
                  className="cockpit-timeline-overlay"
                  ref={timelineRef}
                  style={{ left: `${timelinePos.x}px`, top: `${timelinePos.y}px` }}
                >
                  <div className="cockpit-timeline-overlay-header" onMouseDown={handleTimelineDragStart}>
                    <span>Timeline</span>
                    <div className="cockpit-timeline-overlay-actions">
                      <button
                        className="cockpit-icon-button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setTimelinePos({ x: 0, y: 0 });
                        }}
                      >
                        Reset
                      </button>
                      <button
                        className="cockpit-icon-button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setTimelineOpen(false);
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                  <div className="cockpit-timeline-overlay-body">
                    <TimelinePanel projectId={selectedProjectId} runId={selectedRunId} showHeader={false} />
                  </div>
                </div>
              )}
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
          <EventsPanel projectId={selectedProjectId} runId={selectedRunId} />
          <DoctorPanel projectId={selectedProjectId} runId={selectedRunId} />
          <LaunchPanel projectPath={selectedProject?.path || null} runId={selectedRunId} />
        </div>
      </aside>
    </div>
  );
};

export default CockpitPage;
