import { useEffect, useMemo, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { EventLogEntry, PRD, RunState, LiveFeed } from '../../types/cockpit';

interface TimelinePanelProps {
  projectId: string | null;
  runId: string | null;
  showHeader?: boolean;
}

type PhaseStatus = 'done' | 'active' | 'upcoming' | 'skipped';

const basePhases = ['worker', 'reviewer'];

const TimelinePanel = ({ projectId, runId, showHeader = true }: TimelinePanelProps) => {
  const [events, setEvents] = useState<EventLogEntry[]>([]);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [prd, setPrd] = useState<PRD | null>(null);
  const [live, setLive] = useState<LiveFeed | null>(null);

  useEffect(() => {
    if (!projectId || !runId) {
      setEvents([]);
      setRunState(null);
      setPrd(null);
      setLive(null);
      return;
    }

    const load = async () => {
      try {
        const [eventList, state, prdData, liveData] = await Promise.all([
          cockpitClient.getEvents(projectId, runId, 500),
          cockpitClient.getRunState(projectId, runId),
          cockpitClient.getPRD(projectId, runId),
          cockpitClient.getLiveFeed(projectId, runId, 80),
        ]);
        setEvents(eventList);
        setRunState(state);
        setPrd(prdData);
        setLive(liveData);
      } catch (error) {
        console.error('Failed to load timeline data:', error);
      }
    };

    load();
    const interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, [projectId, runId]);

  const phaseCompletion = useMemo(() => {
    const map = new Map<string, boolean>();
    events.forEach((event) => {
      if (event.type === 'phase_finished' && event.phase && event.iteration !== undefined) {
        map.set(`${event.iteration}-${event.phase}`, true);
      }
    });
    return map;
  }, [events]);

  const totalStories = prd?.stories?.length ?? 0;
  const passedStories = prd?.stories?.filter((story) => story.passes).length ?? 0;
  const maxIterations =
    runState?.maxIterations ??
    (runState?.iteration !== undefined ? runState.iteration + 1 : 1);

  const phases = useMemo(() => {
    const extra: string[] = [];
    const steerEvery = prd?.loop_settings?.steer_every_n_iterations;
    if (steerEvery) {
      extra.push('steering');
    }
    return [...basePhases, ...extra];
  }, [prd]);

  const currentIteration = live?.iteration ?? runState?.iteration ?? null;
  const currentPhase = live?.phase ?? runState?.phase ?? null;

  const statusFor = (iteration: number, phase: string): PhaseStatus => {
    if (currentIteration === iteration && currentPhase === phase) {
      return 'active';
    }
    if (phaseCompletion.get(`${iteration}-${phase}`)) {
      return 'done';
    }
    if (currentIteration !== null && iteration < currentIteration) {
      return 'done';
    }
    return 'upcoming';
  };

  if (!projectId || !runId) {
    return (
      <div className="cockpit-timeline-panel">
        <p className="cockpit-placeholder-text">Select a run to view timeline</p>
      </div>
    );
  }

  return (
    <div className="cockpit-timeline-panel">
      {showHeader && (
        <div className="cockpit-timeline-header">
          <h3 className="cockpit-subsection-title">Timeline</h3>
          <div className="cockpit-timeline-meta">
            <span>Stories: {passedStories}/{totalStories || '—'}</span>
            <span>Iterations: {maxIterations}</span>
          </div>
        </div>
      )}
      <div className="cockpit-timeline-body">
        {Array.from({ length: maxIterations }).map((_, idx) => (
          <div key={idx} className="cockpit-timeline-iteration">
            <div className="cockpit-timeline-line" />
            <div className="cockpit-timeline-node" />
            <div>
              <div className="cockpit-timeline-iter-label">
                Iter {idx}
                {currentIteration === idx && (
                  <span className="cockpit-timeline-current">Current</span>
                )}
              </div>
              <div className="cockpit-timeline-phases">
                {phases.map((phase) => {
                  const status = statusFor(idx, phase);
                  return (
                    <div key={`${idx}-${phase}`} className={`cockpit-timeline-phase ${status}`}>
                      <span className="cockpit-timeline-phase-badge">{phase}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TimelinePanel;
