# Ohmega information architecture (2026-10-20)

The canonical map of what we make and where it lives. The facts behind it are in `site-inventory-2026-10-20.md`.
**Rule: a new product or page must be placed on this map before it ships.**

## 1. What we make: five kinds of thing

| Kind | What it is | Made by | Cadence |
|---|---|---|---|
| **Daily** | One report per desk per day. Each section covers one situation that had news that day. | paid daily runs | geopolitics 2 parts/day (05:30, 17:30 UTC); AI 1/day (09:00) |
| **Situation** (was "theater") | A long-running story's living file. It accumulates every daily section written about it: text, maps, visuals, numbers. | built from dailies, no extra cost | updates whenever a daily writes it up |
| **Article** | Long-form researched piece. | newsroom, run by hand | irregular |
| **Data** | Measured layers, no editorial voice: live map, globe and flows, ships' behaviour, sanctions, calendar, AI benchmarks, countries. | free collectors | minutes to days |
| **Judgments** | What we think will happen, kept on the record and scored: Pulses (0–100 gauges), forecasts vs Polymarket, the paper trader. | model + scoring | daily |

A **desk** is a topic: Geopolitics, AI, more later. Desks own Dailies and Situations. Data and Judgments are shared.

## 2. How a situation works (settled)
- The heat board finds situations from headlines. On a given day the daily writes a section only for situations with something new, so no situation is guaranteed a report every day.
- The situation page is that story's stream: every daily section about it, newest first. Each day appears in full, **with its visuals**, its numbers, grid impact and status log. Below the stream: map, actors, on-the-record, outlook.
- **AI has situations too**, e.g. "the chip export war" or "the frontier lab race". Each desk's situations are listed separately. Heat is never compared across desks, because the scales differ.
- **Spotlight** stays a one-day section in the daily. It only becomes a situation if a second report follows. That stops one-off stories from piling up as permanent "theaters".
- The legacy `technology`-domain AI theaters fold into the AI desk.

## 3. Navigation

Header: **Daily · Situations · Articles · Globe · Data** (logo → Home)

| Route | What |
|---|---|
| `/` | Home: today across desks (headline per desk, situations moving, 3–4 honest numbers, newest article) |
| `/daily` | **Hub of dailies**: one card per desk with today's headline, section list, part 1/2 status and age. Mostly navigation. |
| `/daily/geopolitics/<date>`, `/daily/ai/<date>` | The reports (old `/geopolitics/*` and `/ai/*` redirect here). Visuals always open, never collapsed. |
| `/daily/headlines` | Other outlets' headlines (was `/headlines`), clearly marked unverified |
| `/situations` | Per-desk tabs; each row shows last report, reports to date and state. Active first; quiet ones folded below. |
| `/situations/<id>` | The living file (see §2) |
| `/articles` | as now |
| `/globe` | The HUD (in the nav now, no longer behind the spinner) |
| `/data` | Hub, grouped: **Measured** (live map, maritime, sanctions, calendar, AI benchmarks, countries, statements record) · **Judgments** (Pulses, forecasts + track record merged into one scored page) · **For machines** (API, MCP, feeds) |

Entity pages (events, places, countries) stay where they are, linked from text. Every hub row carries an **as-of age** and a "new since your last visit" dot (localStorage).

## 4. Numbers: the stats registry
Every number shown to readers is registered once, in `sites/ohmega-monster/lib/stats/registry.ts`, with:
- `basis`: `official` | `our_count` | `our_derived` | `model`
- `source`, `scope` (what is counted, and where)
- `coverage` (for `our_count`: why it is a minimum)
- `baseline` + `baseline_since` (whose history and since when)
- `min_history` before a comparison may be shown

Rendering rules, enforced by one `<Stat>` component and the registry:
- `our_count` renders as a minimum ("≥ 3"), with a coverage hover.
- No "vs usual" comparison until our own history meets `min_history`. Before that it says "collecting since 11 Oct".
- `percentile_1y` is shown only with a year of history; otherwise "highest of our N days".
- `model` numbers carry a "model-assessed" mark.
- A cap is never shown as a total ("latest 1,500"); a window is always named.
- An official figure is preferred over our count when both exist for the same thing (Hormuz: PortWatch leads, our AIS is secondary and labelled).
- A check script lists every registered stat and every unregistered numeric render, so the surface can be audited in one place.

## 5. Specific fixes from the audit
Home Hormuz "−100%" (our AIS against an 8-day median) · "military aircraft seen/day" (actually a sum of simultaneous per-region maxima) · fires (4 boxes, not the world) · "world median" (104 profiled states) · grid impact showing 0% while reported damage has no figure · maritime 1000 = row cap · 1500 statements = cap · sanctions windows · `percentile_1y` on young series · duplicate speaker names · theater counts 4/26/20.
