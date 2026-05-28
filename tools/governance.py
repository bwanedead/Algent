#!/usr/bin/env python3
"""Soft static governance for Algent.

Emits *warnings* (and always exits 0) for three classes of structural drift:

1. Module-size pressure  — large files get an escalating nudge to split.
2. Flat package shape    — loose implementation files at a domain package root.
3. Import-boundary drift  — architectural boundaries from docs/ethos crossed.

This is deliberately soft: lint applies pressure, it does not slam hard bumpers.
The boundaries below are objective, but a warning is enough to prompt the right fix.
If we ever want a hard gate, run with ``--strict`` to exit non-zero on any finding.

See docs/linting/static-governance.md for the full rationale.

Run: ``python tools/governance.py``
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------------------
# Paths & configuration
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
PACKAGE_ROOT = BACKEND_ROOT / "algent_backend"

SKIP_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", "dist", "build", "site-packages",
}

# Size pressure (non-blank, non-comment lines).
SIZE_NOTICE = 800
SIZE_STRONG = 1000

# Rail frameworks that must stay confined to the runtime/model-target layers.
RAIL_ROOTS = {"langchain", "langgraph", "langsmith"}
RAIL_ALLOWED_PREFIXES = (
    "algent_backend.agent_system.runtime.adapters",
    "algent_backend.agent_system.foundation.models.targets",
)

# Dotted-prefix anchors for the architectural rules.
DEFINITIONS_PREFIX = "algent_backend.agent_system.definitions"
AGENT_SYSTEM_PREFIX = "algent_backend.agent_system"
GRAPH_OS_PREFIX = "algent_backend.graph_os"
LABS_PREFIX = "algent_backend.labs"
API_PREFIX = "algent_backend.api"
RUNTIME_ADAPTERS_PREFIX = "algent_backend.agent_system.runtime.adapters"
RUNTIME_REGISTRY = "algent_backend.agent_system.runtime.registry"

# Package roots whose top level should be __init__.py + subpackages, not loose modules.
FLAT_WATCH_DIRS = [PACKAGE_ROOT / "agent_system"]
FLAT_ALLOWED = {"__init__.py"}


@dataclass(frozen=True)
class Finding:
    category: str
    location: str
    message: str


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def iter_py_files(root: Path):
    """Yield .py files under ``root``, skipping vendored / cache directories."""
    if not root.exists():
        return
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def module_name(path: Path) -> str:
    """Dotted module name relative to ``backend/`` (e.g. algent_backend.agent_system.x).

    For ``__init__.py`` the package name itself is returned.
    """
    rel = path.relative_to(BACKEND_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def is_package_init(path: Path) -> bool:
    return path.name == "__init__.py"


def count_code_lines(text: str) -> int:
    """Count lines that are neither blank nor pure comments."""
    n = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        n += 1
    return n


def under(dotted: str, prefix: str) -> bool:
    """True if ``dotted`` is ``prefix`` or a submodule of it."""
    return dotted == prefix or dotted.startswith(prefix + ".")


def resolve_relative(module: str | None, level: int, current: str, is_pkg: bool) -> str:
    """Resolve a relative import target to an absolute dotted module name."""
    anchor_parts = current.split(".") if current else []
    if not is_pkg and anchor_parts:
        anchor_parts = anchor_parts[:-1]  # the package containing this module
    # Walk up (level-1) additional packages.
    if level > 1:
        anchor_parts = anchor_parts[: len(anchor_parts) - (level - 1)]
    if module:
        anchor_parts = anchor_parts + module.split(".")
    return ".".join(anchor_parts)


def imported_modules(tree: ast.AST, current: str, is_pkg: bool) -> list[str]:
    """Return absolute dotted module names imported by this file."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                found.append(resolve_relative(node.module, node.level, current, is_pkg))
            elif node.module:
                found.append(node.module)
    return [m for m in found if m]


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------

def check_size(path: Path, text: str, findings: list[Finding]) -> None:
    lines = count_code_lines(text)
    loc = str(path.relative_to(REPO_ROOT))
    if lines >= SIZE_STRONG:
        findings.append(Finding(
            "size", loc,
            f"{lines} code lines (>= {SIZE_STRONG}). Split or reduce before growing further.",
        ))
    elif lines >= SIZE_NOTICE:
        findings.append(Finding(
            "size", loc,
            f"{lines} code lines (>= {SIZE_NOTICE}). Getting large — check for a second responsibility.",
        ))


def check_imports(path: Path, tree: ast.AST, findings: list[Finding]) -> None:
    cur = module_name(path)
    if not cur:
        return
    loc = str(path.relative_to(REPO_ROOT))
    for imp in imported_modules(tree, cur, is_package_init(path)):
        top = imp.split(".", 1)[0]

        # 1. Rail isolation.
        if top in RAIL_ROOTS and not any(under(cur, p) for p in RAIL_ALLOWED_PREFIXES):
            findings.append(Finding(
                "rail-isolation", loc,
                f"imports '{imp}'. Rail frameworks belong only in runtime adapters or "
                f"foundation/models/targets — keep the neutral core rail-free.",
            ))

        # 2. definitions/ purity.
        if under(cur, DEFINITIONS_PREFIX) and under(imp, AGENT_SYSTEM_PREFIX) \
                and not under(imp, DEFINITIONS_PREFIX):
            findings.append(Finding(
                "definitions-purity", loc,
                f"definitions module imports internal '{imp}'. Contracts should depend on nothing.",
            ))

        # 3. graph_os <-> agent_system decoupling.
        if under(cur, AGENT_SYSTEM_PREFIX) and under(imp, GRAPH_OS_PREFIX):
            findings.append(Finding(
                "graph-os-decoupling", loc,
                f"agent_system imports '{imp}'. Keep agent_system and graph_os decoupled "
                f"until a deliberate projection seam exists.",
            ))
        if under(cur, GRAPH_OS_PREFIX) and under(imp, AGENT_SYSTEM_PREFIX):
            findings.append(Finding(
                "graph-os-decoupling", loc,
                f"graph_os imports '{imp}'. Keep graph_os independent of agent_system.",
            ))

        # 4. Transport layering — business logic must not depend up on the api layer.
        if under(imp, API_PREFIX) and any(
            under(cur, p) for p in (AGENT_SYSTEM_PREFIX, GRAPH_OS_PREFIX, LABS_PREFIX)
        ):
            findings.append(Finding(
                "transport-layering", loc,
                f"imports '{imp}'. The api layer is transport; logic must not depend upward on it.",
            ))

        # 5. Adapter seam — adapters are reached only via the runtime registry.
        if under(imp, RUNTIME_ADAPTERS_PREFIX) and cur != RUNTIME_REGISTRY \
                and not under(cur, RUNTIME_ADAPTERS_PREFIX):
            findings.append(Finding(
                "adapter-seam", loc,
                f"imports adapter '{imp}' directly. Reach rail adapters via runtime.registry.",
            ))


def check_flat_packages(findings: list[Finding]) -> None:
    for pkg in FLAT_WATCH_DIRS:
        if not pkg.exists():
            continue
        for child in sorted(pkg.iterdir()):
            if child.is_file() and child.suffix == ".py" and child.name not in FLAT_ALLOWED:
                findings.append(Finding(
                    "flat-package", str(child.relative_to(REPO_ROOT)),
                    "loose module at a domain package root — prefer giving the concern its own subpackage.",
                ))


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------

def collect_findings() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_py_files(PACKAGE_ROOT):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, SyntaxError) as exc:  # skip unreadable / invalid files
            findings.append(Finding("skip", str(path.relative_to(REPO_ROOT)), f"could not parse: {exc}"))
            continue
        check_size(path, text, findings)
        check_imports(path, tree, findings)
    check_flat_packages(findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Soft static governance for Algent.")
    parser.add_argument(
        "--strict", action="store_true",
        help="exit non-zero if any finding is reported (default: soft, always exit 0).",
    )
    args = parser.parse_args(argv)

    findings = collect_findings()
    if not findings:
        print("static governance: no findings.")
        return 0

    by_category: dict[str, list[Finding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    for category in sorted(by_category):
        items = by_category[category]
        print(f"\n[{category}] {len(items)} finding(s):")
        for f in items:
            print(f"  - {f.location}: {f.message}")

    print(f"\nstatic governance: {len(findings)} warning(s). (soft — not blocking)")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
