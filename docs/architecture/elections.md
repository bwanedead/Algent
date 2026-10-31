# Elections feed (polls, poll averages, results)

A free, compounding product that answers the commonest thing the prediction-market bots could not find in the corpus: **what the polls say, and what the count says**
(about 40% of live gap asks were polls or official results: "Likud seat projections", "Senate generic ballot", "Brazil runoff final polls", "Bulgarian CEC results").
Code `backend/algent_backend/elections/`; corpus adapter `corpus/sources/elections.py`; CLI `newsroom elections`; registry product `elections` (job `elections`, daily 01:50 UTC,
free, so the 02:25 corpus build and the 08:45 gap pass see it). **Corpus-only: nothing is published to R2** (tight write budget) and there is no page; the bots read it through the
ordinary `search` / `about` / `entity` / `series` tools. The gap router (`markets/gap_router.py`) sends poll and result asks here instead of to a paid research run.

## What it reads
- **Which elections.** The lookahead calendar's Wikipedia "<year> national electoral calendar" page (`lookahead/sources/elections.py`, `parse_with_pages` also returns each line's linked
  election article). Those held in the last 30 days or due in the next 120 (`flags.LOOKBACK_DAYS` / `LOOKAHEAD_DAYS`), nearest first, at most `MAX_ELECTIONS` (60). Plus elections named in
  recent poll / result asks of the bots: the CLI reads the gap ledger (this package never imports markets), skips asks a calendar election already covers, and resolves the rest with one
  Wikipedia search each (`MAX_ASK_SEARCHES`, 5 a run).
- **Which pages.** `Opinion polling for the <election>` and the election's own article, both via `action=raw` through `polite_http` (paced, memoised); one `#REDIRECT` hop is followed; a
  missing page is "no polls page", not an error. If there is no separate polling page the election article's own polling tables are used.

## What it extracts
- **Polls** (`polls.py`). A table is a poll table when its header has a pollster and a fieldwork-date column and at least two party/candidate columns (multi-row headers and
  `rowspan`/`colspan` are expanded by `wikitext.grid`). Per row: pollster, fieldwork text and its end date, sample size, a share per party (percent, or seats when the section heading says
  seats or whole numbers add up to more than 100), and the non-party numbers (others, undecided, lead) kept apart. Dates without a year take the year band row above or the election's year.
  A row whose date or shares do not read is stored as **raw cells** (`uncertain`), never guessed or dropped; the 2022-style "previous election" row is skipped.
- **Recent average** (`polls.average`). Per party, the mean over the newest `AVERAGE_LAST_N` (5) readable polls of the table that carry the party; a party missing from a poll is skipped, not
  counted as zero; others/undecided/lead never enter. Reported with the poll count, the date span and the pollsters used. Our arithmetic over reported figures: basis `our_derived`.
- **Results** (`results.py`). The first table under a "Results" heading with a votes or seats column: name (and party for a candidate table), votes, percent, seats; total / valid / invalid /
  turnout rows go to `totals`. **Status** is read from the words around the table: `preliminary` (preliminary, provisional, partial, unofficial, "x% of votes counted"), `official` (official,
  final, certified results), else `unstated`. Preliminary wins a tie.

## What it stores
`elections_store/snapshots/<slug>.jsonl`, append-only, one `Snapshot` per election per *change* (a hash of the content, not of the read time, so an unchanged page adds nothing). Each
carries `acquired_at`, the page URLs, the licence (CC BY-SA 4.0, Wikipedia contributors) and confidence `medium` (volunteer-compiled). History is never overwritten: the as-of record of what the
polls said on each day is the compounding asset. Backed up (small; irreplaceable as an as-of read). Budget and growth are in the registry entry.

## How the bots reach it
`corpus/sources/elections.py`, one unit per election. Stable ids: `election:<slug>:avg:<day>` (the average as read that day; `:t2` for a second table), `election:<slug>:poll:<day>:<pollster>`
(newest 20 polls per table), `election:<slug>:result:<day>`. The country is mentioned by id (`country:XX`, from the calendar or the title's demonym, `country.py`); parties are weak `org` entities
and candidates `person` entities, so `entity("Likud")` / `about("Likud")` reach every poll naming them and merge with the same party from other sources. Each party's average is also a series
`election.avg.<slug>`. Document text says the source and licence in words.

## Known gaps
- Headers made only of images/templates (no text) leave a party column unnamed; if fewer than two named columns remain the table is not recognised.
- Ranges in a share cell ("29-31") read as the first number; a `<1` is dropped; scenario tables (head-to-head, hypothetical) are separate tables, each with its own average.
- Dates across a year boundary without a year band can take the wrong year.
- One Wikipedia language and the pages' own coverage: smaller elections often have no polling page. Polls for US states and multi-race elections are per page.
- No weighting by pollster quality, sample size or recency beyond "newest N".
