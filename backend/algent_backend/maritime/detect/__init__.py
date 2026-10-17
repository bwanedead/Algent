"""One module per behaviour. Each exposes ``detect(ctx, ...) -> list[BehaviourEvent]``: a pure function of the pass context (profile book,
coverage, fresh board, exclusions) and, where it needs memory between passes, a small state dict the watch persists."""
