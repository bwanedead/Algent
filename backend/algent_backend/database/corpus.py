"""
Load the research corpus into Postgres (migrations/002): every profile as a JSONB document, plus
every revision in its history — the profile store's append-only record, preserved.

Idempotent: a profile already loaded at the same revision is left alone; a newer revision updates
the current row and adds a revision row. Nothing is ever deleted.

    python -m algent_backend.database load-profiles
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _rows(store: Any) -> list[tuple[dict, list[dict]]]:
    """(current profile, [every historical revision]) for each profile in the store."""
    out = []
    for pid in store.list_ids():
        profile = store.get(pid)
        if profile is None:
            continue
        history = []
        for path in store.history(pid):
            try:
                history.append(json.loads(Path(path).read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        out.append((profile.model_dump(), history))
    return out


def load_profiles(conn: Any = None) -> dict:
    from algent_backend.agent_system.agents.research.store import JsonProfileStore

    from .migrate import connect

    conn = conn or connect()
    loaded = revisions = 0
    for current, history in _rows(JsonProfileStore()):
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""insert into research_profiles
                                 (id, title, revision, as_of, profile_status, generated_at, payload, updated_at)
                               values (%s, %s, %s, %s, %s, %s, %s, now())
                               on conflict (id) do update set title = excluded.title,
                                 revision = excluded.revision, as_of = excluded.as_of,
                                 profile_status = excluded.profile_status, payload = excluded.payload,
                                 updated_at = now()
                               where research_profiles.revision < excluded.revision""",
                            (current["id"], current.get("title") or "", int(current.get("revision") or 1),
                             str(current.get("as_of") or ""), str(current.get("profile_status") or ""),
                             current.get("generated_at") or None, json.dumps(current)))
                loaded += cur.rowcount
                for doc in [*history, current]:
                    cur.execute("""insert into research_profile_revisions (profile_id, revision, payload)
                                   values (%s, %s, %s) on conflict do nothing""",
                                (current["id"], int(doc.get("revision") or 1), json.dumps(doc)))
                    revisions += cur.rowcount
    return {"profiles_written": loaded, "revisions_added": revisions}
