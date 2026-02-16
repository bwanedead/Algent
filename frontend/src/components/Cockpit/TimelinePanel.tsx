import { useEffect, useMemo, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { EventLogEntry, PRD, RunState, LiveFeed, OrchestrationState } from '../../types/cockpit';

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
  const [orchestration, setOrchestration] = useState<OrchestrationState | null>(null);

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
        const [eventList, state, prdData, liveData, orchestrationData] = await Promise.all([
          cockpitClient.getEvents(projectId, runId, 500),
          cockpitClient.getRunState(projectId, runId),
          cockpitClient.getPRD(projectId, runId),
          cockpitClient.getLiveFeed(projectId, runId, 80),
          cockpitClient.getOrchestration(projectId, runId),
        ]);
        setEvents(eventList);
        setRunState(state);
        setPrd(prdData);
        setLive(liveData);
        setOrchestration(orchestrationData);
        console.log('[cockpit][timeline]', {
          events: eventList.length,
          scheme: orchestrationData?.scheme,
          cursor: orchestrationData?.cursor,
          maxIterations: state?.maxIterations ?? null,
        });
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
  const latestRunStartedMaxIterations = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const event = events[i];
      if (event.type !== 'run_started') continue;
      const value = event.data?.max_iterations;
      if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
        return Math.trunc(value);
      }
    }
    return null;
  }, [events]);
  const observedMaxIteration = useMemo(() => {
    let maxIteration = -1;
    for (const event of events) {
      if (typeof event.iteration === 'number' && event.iteration > maxIteration) {
        maxIteration = event.iteration;
      }
    }
    if (typeof runState?.iteration === 'number' && runState.iteration > maxIteration) {
      maxIteration = runState.iteration;
    }
    if (typeof live?.iteration === 'number' && live.iteration > maxIteration) {
      maxIteration = live.iteration;
    }
    return maxIteration;
  }, [events, live, runState]);

  const maxIterations =
    latestRunStartedMaxIterations ??
    runState?.maxIterations ??
    (observedMaxIteration >= 0 ? observedMaxIteration + 1 : 12);

  const phases = useMemo(() => {
    const scheme = orchestration?.scheme;
    if (!scheme) return [];
    const expanded: string[] = [];
    const normalized = scheme.toUpperCase();
    const pattern = /([WR])(\d*)/g;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(normalized)) !== null) {
      const code = match[1];
      const count = match[2] ? Number(match[2]) : 1;
      const phase = code === 'W' ? 'worker' : 'reviewer';
      const repeat = Number.isFinite(count) && count > 0 ? count : 1;
      for (let i = 0; i < repeat; i += 1) {
        expanded.push(phase);
      }
    }
    return expanded;
  }, [orchestration]);

  const activeFromEvents = useMemo(() => {
    let active: { iteration: number; phase: string } | null = null;
    for (const event of events) {
      if (
        event.type === 'phase_started' &&
        typeof event.iteration === 'number' &&
        typeof event.phase === 'string'
      ) {
        active = { iteration: event.iteration, phase: event.phase };
      }
      if (
        event.type === 'phase_finished' &&
        typeof event.iteration === 'number' &&
        typeof event.phase === 'string' &&
        active &&
        active.iteration === event.iteration &&
        active.phase === event.phase
      ) {
        active = null;
      }
    }
    return active;
  }, [events]);

  const currentIteration = activeFromEvents?.iteration ?? live?.iteration ?? runState?.iteration ?? null;
  const currentPhase = activeFromEvents?.phase ?? live?.phase ?? runState?.phase ?? null;

  const schedulePhaseForIteration = (iteration: number): string => {
    if (!phases.length) return 'unknown';
    const firstEvent = events
      .filter((event) => event.type === 'phase_started' && event.phase && event.iteration !== undefined)
      .sort((a, b) => (a.iteration ?? 0) - (b.iteration ?? 0))[0];

    let baseOffset = 0;
    if (firstEvent?.phase && firstEvent.iteration !== undefined) {
      const idx = phases.indexOf(firstEvent.phase);
      if (idx >= 0) {
        baseOffset = (idx - firstEvent.iteration + phases.length) % phases.length;
      }
    } else if (orchestration?.cursor !== undefined) {
      baseOffset = orchestration.cursor % phases.length;
    }

    const schemeIndex = (baseOffset + iteration) % phases.length;
    return phases[schemeIndex];
  };

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
            <span>Scheme: {orchestration?.scheme || 'unset'}</span>
            {orchestration?.cursor !== undefined && <span>Cursor: {orchestration.cursor}</span>}
          </div>
        </div>
      )}
      <div className="cockpit-timeline-body">
        {Array.from({ length: maxIterations }).map((_, idx) => {
          const scheduledPhase = schedulePhaseForIteration(idx);
          const status = statusFor(idx, scheduledPhase);
          const reviewMode =
            events.find(
              (event) =>
                event.type === 'phase_started' &&
                event.phase === 'reviewer' &&
                event.iteration === idx,
            )?.data?.review_mode || null;
          const phaseLabel = reviewMode ? `${scheduledPhase} (${reviewMode})` : scheduledPhase;
          return (
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
                  <div className={`cockpit-timeline-phase ${status}`}>
                    <span className="cockpit-timeline-phase-badge">{phaseLabel}</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TimelinePanel;
