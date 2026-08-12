# Radar — the always-on lane

Radar posts short notices to X off the t0 discovery pool. No article, no research rail: a pool
item becomes one plain sentence and goes in a queue that drains on a timer.

It runs until told otherwise, and the most important thing on this page is that **turning it off
always works**.

## The four commands

From the repo root (`radar.cmd` on Windows, `./radar` elsewhere):

```
radar start     begin. Runs in the background; close the terminal freely.
radar stop      stop, and verify nothing is left running.
radar status    what is queued, what is running, when the next post goes.
radar log       follow the log.
```

`radar start` accepts `--discovery-every N` and `--post-every N` in minutes. Defaults: discovery
every **120**, a post about every **60** (jittered ±15, so roughly 45–75 — never on the hour every
hour, which reads as a bot).

## Turning it off

`radar stop` writes a stop file, waits for the loop to exit, and **force-kills the process tree
if it does not**. It then re-checks the process table and reports `verified_not_running`. That
answer comes from the OS, not from the daemon's own claim.

Three things are true by design:

- **Closing your laptop is a valid way to stop it.** Nothing is lost. The queue is on disk, and
  `radar status` will say it is not running.
- **Stopping mid-discovery is safe.** The t0 child is killed with the tree and its run lock is
  cleared; if anything is left behind, the next run's stale-pid recovery reclaims it.
- **Stopping something already dead is success, not an error.** The panic button never fails
  because the thing already fell over.

If you ever want to be certain without trusting any of this, the daemon's pid is in
`backend/runs_data/radar_daemon.json` — kill it however you like. Radar keeps no state that a
hard kill can corrupt.

## Checking on it without an agent

`radar status` is the whole picture: whether it is running, how many posts are queued, when the
next one goes, how many have been sent this session, and the last few errors.

`radar log` follows `backend/runs_data/radar_daemon.log`, which records every discovery, every
post with its URL, and every failure. A post that fails **stays queued** and is retried on the
next cycle rather than being dropped.

## What it does on a cycle

1. **Discovery** (every ~2h): builds a fresh t0 pool, then sweeps it — one cheap model call that
   picks the few items worth saying out loud and writes each as a single sentence.
2. **Release** (about hourly): sends **one** due post. One at a time is what keeps the cadence
   from clumping.

Posts are deduplicated by their source t0 item, so re-sweeping the same pool queues nothing new.

## Rules it follows

- No `BREAKING:`, no urgency markers, no engagement bait.
- No liveness claims. It cannot tell how old a pool item is, so it does not guess.
- Confidence lives inside the sentence, never as a caveat bolted on after — *"Musk says X, and a
  two-word reply is the only public detail"*, not *"X. But nobody has confirmed X."*
- One thought per post.
- Posting nothing is a normal outcome. A quiet sweep beats filler.

## Independence from the article rail

Radar and editorial do not know about each other, on purpose. The same story may be posted here
and also become an article, or either, or neither. Coupling them would let one lane silently veto
the other.

## The one real constraint

**Only one machine may run radar.** The queue is a local file, so two machines sweeping the same
pool would post the same items twice. If you ever move this to an always-on box, move it
wholesale — do not run it in both places.
