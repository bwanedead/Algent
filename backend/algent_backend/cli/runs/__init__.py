"""
Runs CLI — the operator/agent control plane over the harness.

Every command prints exactly one JSON document to stdout, so humans, scripts,
and other agents (including headless CLI harnesses) are equal callers.

Constitutional rule (see docs/architecture/run-control-plane.md): the CLI may
expose, observe, and trigger harness behavior; it must never define what that
behavior means. Run lifecycle truth lives in the harness and its run files —
the CLI only reads them and launches processes.
"""
