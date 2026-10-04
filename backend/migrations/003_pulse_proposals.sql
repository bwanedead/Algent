-- 003 — the Pulse proposals ledger (pulse/registry.py).
--
-- Anyone may propose a Pulse; a proposal that recurs becomes one. Every line (a sighting, a
-- promotion, a duplicate verdict) is appended and never changed: recurrence is counted from the
-- ledger, so rewriting it would rewrite what counts as evidence. `body` is the whole line as JSON;
-- the columns beside it are what the ledger is queried by.

create table pulse_proposals (
    seq          bigserial primary key,
    proposal_id  text not null,
    kind         text not null check (kind in ('sighting', 'promoted', 'duplicate')),
    at           timestamptz not null,
    body         jsonb not null,
    recorded_at  timestamptz not null default now()
);
create index pulse_proposals_by_id on pulse_proposals(proposal_id);

create function forbid_proposal_mutation() returns trigger language plpgsql as $$
begin
    raise exception 'pulse_proposals is append-only (% refused)', tg_op;
end;
$$;
create trigger pulse_proposals_append_only
    before update or delete on pulse_proposals
    for each row execute function forbid_proposal_mutation();

alter table pulse_proposals enable row level security;
