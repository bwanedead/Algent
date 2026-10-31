"""
Elections feed: polling averages, individual polls and results as citable documents, one unit per election.

Ids are stable and carry the date they describe: ``election:<slug>:avg:<day>`` (the recent average as read on that day, one per day we read it; a second table is
``...:avg:<day>:t2``), ``election:<slug>:poll:<day>:<pollster>`` (the newest ``flags.INDEX_POLLS_PER_TABLE`` polls of each table) and
``election:<slug>:result:<day>`` (the results table as read that day: they change while votes are counted). The country is mentioned by id; parties and
candidates are declared as weakly-ranked ``org`` / ``person`` entities, so ``entity("Likud")`` and ``about("Likud")`` reach every poll that names them and a
party the corpus already knows from another source merges with it. Each party's average is also a series (``election.avg.<slug>``, basis ``our_derived``:
our mean of reported polls). Every document names its Wikipedia source and licence in words; confidence is medium.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from algent_backend.elections import flags as ef
from algent_backend.elections import store
from algent_backend.elections.collect import current
from algent_backend.elections.contracts import Poll, PollTable, Snapshot

from .. import flags
from ..norm import slug
from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, tree_mark

_NOT_A_PARTY = ("other", "undecided", "none", "don't know", "dk", "lead", "abstain", "blank")
_NOTE = f"Source: Wikipedia ({ef.LICENSE}), compiled by volunteers; medium confidence."


def _figure(v: float, unit: str) -> str:
    return f"{v:g} seats" if unit == "seats" else f"{v:.1f}%"


def _party(sink: Sink, name: str, doc: str, role: str, day: str, *, person: bool = False) -> None:
    if not name or name.casefold().startswith(_NOT_A_PARTY):
        return
    pid = f"{'person' if person else 'org'}:{slug(name)}"
    sink.declare(pid, "person" if person else "org", name, rank=flags.RANK_MENTIONED)
    sink.mention(entity=pid, document=doc, role=role, date=day)


def _average(snap: Snapshot, table: PollTable, idx: int, sink: Sink) -> None:
    avg, day = table.average, snap.acquired_at[:10]
    if avg is None:
        return
    doc = f"election:{snap.slug}:avg:{day}" + (f":t{idx + 1}" if idx else "")
    shares = ", ".join(f"{k} {_figure(v, avg.unit)}" for k, v in sorted(avg.shares.items(), key=lambda kv: -kv[1]))
    kind = "seat projections" if avg.unit == "seats" else "opinion polls"
    sink.document(doc, "election_poll_average", date=day, title=f"{snap.election}: polling average, {kind}, {day}", url=snap.pages.get("polling") or snap.pages.get("election", ""),
                  status="medium confidence",
                  body=f"Polling average for the {snap.election} ({table.heading or 'opinion polling'}): the mean of the newest {avg.n_polls} polls, fieldwork {avg.first} to {avg.last}, "
                       f"read {day}. {shares}. Pollsters: {', '.join(avg.pollsters)}. {_NOTE}")
    if snap.country:
        sink.mention(entity=country_id(snap.country), document=doc, role="election polled", date=day)
    for name, v in avg.shares.items():
        _party(sink, name, doc, "party polled", day)
        if not name.casefold().startswith(_NOT_A_PARTY):
            sink.observation(f"election.avg.{snap.slug}", day, v, entity=f"org:{slug(name)}", unit="seats" if avg.unit == "seats" else "percent", basis="our_derived",
                             label=f"{name} polling average, {snap.election}", source_url=snap.pages.get("polling") or snap.pages.get("election", ""),
                             note=f"mean of {avg.n_polls} polls; {_NOTE}")


def _poll(snap: Snapshot, table: PollTable, idx: int, p: Poll, sink: Sink, seen: set[str]) -> None:
    doc = f"election:{snap.slug}:poll:{p.date}:{slug(p.pollster, limit=30)}" + (f":t{idx + 1}" if idx else "")
    while doc in seen:                                                   # two scenarios by one firm on one day
        doc += "+"
    seen.add(doc)
    figures = ", ".join(f"{k} {_figure(v, p.unit)}" for k, v in sorted(p.shares.items(), key=lambda kv: -kv[1]))
    others = "; ".join(f"{k} {v:g}" for k, v in p.others.items())
    sink.document(doc, "election_poll", date=p.date, title=f"{snap.election}: {p.pollster} poll, {p.date}", url=snap.pages.get("polling") or snap.pages.get("election", ""),
                  status="medium confidence",
                  body=f"{p.pollster} {'seat projection' if p.unit == 'seats' else 'opinion poll'} for the {snap.election}, fieldwork {p.fieldwork}"
                       f"{f', sample {p.sample}' if p.sample else ''}. {figures}.{f' Also: {others}.' if others else ''} {_NOTE}")
    if snap.country:
        sink.mention(entity=country_id(snap.country), document=doc, role="election polled", date=p.date)
    for name in p.shares:
        _party(sink, name, doc, "party polled", p.date)


def _result(snap: Snapshot, sink: Sink) -> None:
    res, day = snap.results, snap.acquired_at[:10]
    if res is None:
        return
    doc = f"election:{snap.slug}:result:{day}"
    rows = "; ".join(" ".join(x for x in (r.name, f"{r.votes:,} votes" if r.votes is not None else "", f"{r.percent:g}%" if r.percent is not None else "",
                                          f"{r.seats} seats" if r.seats is not None else "") if x) for r in res.rows[:12])
    totals = ", ".join(f"{k} {v:,.0f}" for k, v in res.totals.items())
    stated = f"The page calls these figures {res.status}" + (f" (\"{res.status_note}\")" if res.status_note else "") if res.status != "unstated" else "The page does not say whether these figures are official or preliminary"
    sink.document(doc, "election_result", date=day, title=f"{snap.election}: results ({res.status}), read {day}", url=snap.pages.get("election", ""), status=res.status,
                  body=f"Results of the {snap.election} as read on {day}. {stated}. {rows}. {totals + '. ' if totals else ''}{_NOTE}")
    if snap.country:
        sink.mention(entity=country_id(snap.country), document=doc, role="election held", date=day)
    for r in res.rows:
        if r.party:                                                      # a candidate table: the name is a person, the party column is the party
            _party(sink, r.name, doc, "candidate in results", day, person=True)
            _party(sink, r.party, doc, "party in results", day)
        else:
            _party(sink, r.name, doc, "party in results", day)


def _emit(slug_: str, sink: Sink) -> None:
    snaps = store.snapshots(slug_)
    by_day: dict[str, Snapshot] = {s.acquired_at[:10]: s for s in snaps}          # the last read of a day stands for the day
    seen: set[str] = set()
    for s in by_day.values():
        for i, t in enumerate(s.polls):
            _average(s, t, i, sink)
        _result(s, sink)
    if snaps:
        for i, t in enumerate(snaps[-1].polls):                                  # individual polls repeat across snapshots: the newest read has the most
            for p in [p for p in t.polls if not p.uncertain and p.date][:ef.INDEX_POLLS_PER_TABLE]:
                _poll(snaps[-1], t, i, p, sink, seen)


def _units() -> Iterator[Unit]:
    for s in store.slugs():
        snaps = store.snapshots(s)
        if snaps and not current(snaps[-1].election, date.today()):                 # a past election found by an over-wide search stays out of the corpus
            continue
        yield Unit(f"election:{s}", digest_of([x.digest() for x in snaps] + [x.acquired_at[:10] for x in snaps]), lambda sink, s=s: _emit(s, sink),
                   date=snaps[-1].acquired_at[:10] if snaps else "", path=f"elections_store/snapshots/{s}.jsonl")


def _watermark() -> str:
    return tree_mark(store.root() / "snapshots", "*.jsonl") or "none"


SOURCE = Source("elections", "elections", _units, _watermark)
