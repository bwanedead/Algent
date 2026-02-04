import { useEffect, useState } from 'react';
import { cockpitClient } from '../../client/cockpitClient';
import type { EventLogEntry } from '../../types/cockpit';

interface EventsPanelProps {
  projectId: string | null;
  runId: string | null;
}

const EventsPanel = ({ projectId, runId }: EventsPanelProps) => {
  const [events, setEvents] = useState<EventLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [autoFollow, setAutoFollow] = useState(false);

  // Load events when runId changes
  useEffect(() => {
    if (!projectId || !runId) {
      setEvents([]);
      return;
    }

    const loadEvents = async () => {
      setLoading(true);
      try {
        const eventList = await cockpitClient.getEvents(projectId, runId, 50);
        setEvents(eventList);
      } catch (error) {
        console.error('Failed to load events:', error);
      } finally {
        setLoading(false);
      }
    };

    loadEvents();
  }, [projectId, runId]);

  // Auto-follow functionality
  useEffect(() => {
    if (!autoFollow || !projectId || !runId) return;

    const interval = setInterval(async () => {
      try {
        const eventList = await cockpitClient.getEvents(projectId, runId, 50);
        setEvents(eventList);
      } catch (error) {
        console.error('Failed to refresh events:', error);
      }
    }, 2000); // Refresh every 2 seconds

    return () => clearInterval(interval);
  }, [autoFollow, projectId, runId]);

  // Manual refresh
  const handleRefresh = async () => {
    if (!projectId || !runId) return;

    setLoading(true);
    try {
      const eventList = await cockpitClient.getEvents(projectId, runId, 50);
      setEvents(eventList);
    } catch (error) {
      console.error('Failed to refresh events:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!projectId || !runId) {
    return (
      <div className="cockpit-events-panel">
        <p className="cockpit-placeholder-text">Select a run to view events</p>
      </div>
    );
  }

  return (
    <div className="cockpit-events-panel">
      <div className="cockpit-events-header">
        <h3 className="cockpit-subsection-title">Events</h3>
        <div className="cockpit-events-controls">
          <button
            className="cockpit-events-button"
            onClick={handleRefresh}
            disabled={loading}
          >
            Refresh
          </button>
          <label className="cockpit-events-toggle">
            <input
              type="checkbox"
              checked={autoFollow}
              onChange={(e) => setAutoFollow(e.target.checked)}
              className="cockpit-control-checkbox"
            />
            <span className="cockpit-events-toggle-label">Auto-follow</span>
          </label>
        </div>
      </div>

      <div className="cockpit-events-list">
        {events.length === 0 ? (
          <p className="cockpit-placeholder-text">No events found</p>
        ) : (
          events.map((event, index) => (
            <div key={index} className="cockpit-event-item">
              <div className="cockpit-event-header">
                <span className={`cockpit-event-level ${event.level.toLowerCase()}`}>
                  {event.level}
                </span>
                <span className="cockpit-event-timestamp">
                  {new Date(event.timestamp).toLocaleString()}
                </span>
              </div>
              <div className="cockpit-event-message">{event.message}</div>
              {(event.phase || event.iteration !== undefined) && (
                <div className="cockpit-event-meta">
                  {event.phase && <span>Phase: {event.phase}</span>}
                  {event.iteration !== undefined && <span>Iteration: {event.iteration}</span>}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default EventsPanel;
