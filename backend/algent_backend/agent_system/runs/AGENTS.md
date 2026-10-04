# runs / control_plane — local notes

- **Stop a hung run with tree-kill:** `python -m algent_backend.cli runs stop --run-id …`
  (uses `taskkill /T` on Windows). Killing only the parent PID can leave nested
  `codex`/`grok`/node children alive and eating RAM.
- Nested CLI spawns (analytics harness, optional X grok lanes) go through
  `control_plane/process_tree.run_capturing` so timeouts also tree-kill.
- Foreground `newsroom run --compose` is in-process; orphans come from nested CLIs,
  not from a detached compose child.
