-- 001 — Ohmega Pulse: situations, versioned Pulse rulers, the append-only influence ledger,
-- events and watches. Design: docs/architecture/pulse-system.md.
--
-- The influence ledger is the truth. pulse_state is a cache of its replay and may be rebuilt at
-- any time. Row-level security is on for every table with NO policies: until something is
-- deliberately published, only the backend's own credential can read or write.

create table situations (
    id          text primary key,                       -- sit_russia_nato
    domain      text not null default 'geopolitics',    -- domain-agnostic machinery
    title       text not null,
    summary     text not null default '',
    entities    jsonb not null default '[]'::jsonb,     -- canonical names / aliases covered
    parent_id   text references situations(id),         -- set when split from a broader one
    status      text not null default 'active' check (status in ('active', 'dormant', 'merged')),
    created_at  timestamptz not null default now()
);

create table pulses (
    id            text primary key,                     -- pls_russia_nato_military
    situation_id  text not null references situations(id),
    name          text not null,
    status        text not null default 'experimental'
                  check (status in ('experimental', 'active', 'dormant')),
    created_at    timestamptz not null default now()
);
create index pulses_situation on pulses(situation_id);

-- The frame: the question plus the calm (0) and extreme (100) ends. Between them the scale is the
-- Pulse's own history of readings (doctrine v3). A new frame is a new version; old versions are
-- never edited, because every influence records the version it was measured with.
create table pulse_definitions (
    pulse_id    text not null references pulses(id),
    version     integer not null check (version >= 1),
    question    text not null,
    low_end     text not null default '',
    high_end    text not null default '',
    anchors     jsonb not null default '[]'::jsonb,     -- legacy fixed-ruler seeds only
    note        text not null default '',
    created_at  timestamptz not null default now(),
    primary key (pulse_id, version)
);

create table events (
    id           text primary key,
    occurred_on  date,
    place        text not null default '',
    actors       jsonb not null default '[]'::jsonb,
    summary      text not null,
    claim_refs   jsonb not null default '[]'::jsonb,     -- [{profile_id, claim_id}]
    sources      jsonb not null default '[]'::jsonb,     -- every research sighting of this event
    created_at   timestamptz not null default now()
);

-- Freshness: daily headline-radar sightings per situation. They make a Pulse stale; they never
-- move one (unverified headlines are not evidence).
create table radar_sightings (
    situation_id  text not null references situations(id),
    key           text not null,                         -- <edition>:<vector id>
    at            timestamptz not null,
    edition       text not null,
    headline      text not null,
    primary key (situation_id, key)
);

create table situation_events (
    situation_id  text not null references situations(id),
    event_id      text not null references events(id),
    primary key (situation_id, event_id)
);

create table pulse_influences (
    key                  text primary key,               -- pulse + event + run + mode: idempotent
    pulse_id             text not null,
    at                   timestamptz not null,
    evidence_through     date,
    mode                 text not null check (mode in ('seed', 'article', 'reassess', 'blind')),
    definition_version   integer not null,
    proposed_position    numeric(5, 1) check (proposed_position between 0 and 100),
    absolute_position    numeric(5, 1) check (absolute_position between 0 and 100),   -- history-free read: one vote
    decision             text not null check (decision in ('applied', 'no_change', 'rejected', 'reconcile')),
    rationale            text not null,
    confidence           jsonb not null default '{}'::jsonb,   -- quality / coverage / agreement
    source               jsonb not null default '{}'::jsonb,   -- run, stage, profile, article, claims, event
    prompt_version       text not null default '',
    model                text not null default '',
    watch_ids_triggered  jsonb not null default '[]'::jsonb,
    recorded_at          timestamptz not null default now(),
    foreign key (pulse_id, definition_version) references pulse_definitions(pulse_id, version)
);
create index pulse_influences_pulse_at on pulse_influences(pulse_id, at);

-- Append-only, enforced where it cannot be bypassed by a careless caller.
create function forbid_ledger_mutation() returns trigger language plpgsql as $$
begin
    raise exception 'pulse_influences is append-only (% refused)', tg_op;
end;
$$;
create trigger pulse_influences_append_only
    before update or delete on pulse_influences
    for each row execute function forbid_ledger_mutation();

-- Cache of the ledger's replay (pulse/projection.py). Always rebuildable; never the truth.
create table pulse_state (
    pulse_id     text primary key references pulses(id),
    state        jsonb not null,
    computed_at  timestamptz not null default now()
);

create table watches (
    id                  text primary key,
    situation_id        text not null references situations(id),
    condition           text not null,
    why                 text not null default '',
    evidence_needed     text not null default '',
    expected_direction  text not null default 'either' check (expected_direction in ('up', 'down', 'either')),
    horizon             date,
    origin_positions    jsonb not null default '{}'::jsonb,
    status              text not null default 'open'
                        check (status in ('open', 'triggered', 'expired', 'invalidated')),
    created_at          timestamptz not null default now(),
    resolved_at         timestamptz,
    resolved_by         jsonb
);

create table pulse_watches (
    pulse_id  text not null references pulses(id),
    watch_id  text not null references watches(id),
    primary key (pulse_id, watch_id)
);

-- A watch resolves once: open -> a terminal state, never back, never twice.
create function watch_resolves_once() returns trigger language plpgsql as $$
begin
    if old.status <> 'open' and new.status is distinct from old.status then
        raise exception 'watch % is already %', old.id, old.status;
    end if;
    return new;
end;
$$;
create trigger watches_resolve_once before update on watches
    for each row execute function watch_resolves_once();

alter table situations        enable row level security;
alter table pulses            enable row level security;
alter table pulse_definitions enable row level security;
alter table events            enable row level security;
alter table situation_events  enable row level security;
alter table pulse_influences  enable row level security;
alter table pulse_state       enable row level security;
alter table watches           enable row level security;
alter table pulse_watches     enable row level security;
alter table radar_sightings   enable row level security;
