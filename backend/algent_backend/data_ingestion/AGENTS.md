# data_ingestion — local notes

- **Two menus.** t0/pool = raw leads (`--compose` / `--pool-menu`). synthesis/vector = research angles (`--pick`). Never treat their numbers as the same list. Full rules: `cli/newsroom/AGENTS.md`.
- **Discovery menus in chat are literal and complete.** Paste every numbered line. Never condense, summarize, range-collapse (`16–38`), or say “see file.” If synthesis ran, paste **full t0 + full synthesis** menus, both labeled. English + `orig:` lines both stay.
- Menu printer: `cli/t0.py` `print_menu` (no label truncation; `signals.label_en` when non-English). Vector menu: `cli/newsroom/pipeline.py` `print_vector_menu`.
- **`--compose` must not rebuild t0.** It reuses the latest pool so pick numbers stay valid; only `--fresh` rebuilds discovery.
- **X is off by default in t0** (`DEFAULT_CHANNELS` omits `x`). Re-enable with `--channels …,x` or `ALGENT_T0_CHANNELS`.
- **Synthesis defaults OFF** via `agent_system/agents/newsroom/flags.py` (`SYNTHESIS_ENABLED`). Agents flip that file — do not ask the human to set `.env`. Optional one-shot: `ALGENT_SYNTHESIS=0/1`.
