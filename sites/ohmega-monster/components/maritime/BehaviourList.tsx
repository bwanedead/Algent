import { kindLabel, type MaritimeEvent } from "@/lib/maritime-shared";

import EventDetail from "./EventDetail";

import "./maritime.css";

// A vessel's behaviour history, newest first, each event in full (a vessel place page). Plain server component: no state.

export default function BehaviourList({ events, nowMs }: { events: MaritimeEvent[]; nowMs: number }) {
  return (
    <ul className="mb-list" aria-label="Behaviour seen">
      {events.map((e) => (
        <li key={e.id} id={e.id} aria-label={`${kindLabel(e.kind)} ${e.started_at.slice(0, 10)}`}>
          <EventDetail e={e} nowMs={nowMs} />
        </li>
      ))}
    </ul>
  );
}
