"""Deterministic package boundaries for Intellex, Mathesys, and QnGen.

Allowed:
  mathesys → intellex
  qngen → intellex

Forbidden:
  intellex → mathesys | qngen
  mathesys → qngen
  qngen → mathesys

Composition in worker/services/routers is out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
PACKAGES = ("intellex", "mathesys", "qngen")

FORBIDDEN: dict[str, frozenset[str]] = {
    "intellex": frozenset({"mathesys", "qngen"}),
    "mathesys": frozenset({"qngen"}),
    "qngen": frozenset({"mathesys"}),
}


def _imported_packages(node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)
    elif isinstance(node, ast.ImportFrom) and node.module:
        names.append(node.module)
    return names


def _peer_hits(module_name: str, forbidden: frozenset[str]) -> list[str]:
    hits: list[str] = []
    for peer in forbidden:
        prefixes = (f"app.{peer}", peer)
        if module_name == peer or any(
            module_name == p or module_name.startswith(f"{p}.") for p in prefixes
        ):
            hits.append(peer)
    return hits


def _violations_in_file(path: Path, package: str) -> list[str]:
    forbidden = FORBIDDEN[package]
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = path.relative_to(APP_ROOT)
    found: list[str] = []
    for node in ast.walk(tree):
        for module_name in _imported_packages(node):
            for peer in _peer_hits(module_name, forbidden):
                found.append(f"{rel}: imports {module_name} (forbidden {package} → {peer})")
    return found


def test_foundry_system_import_boundaries() -> None:
    violations: list[str] = []
    for package in PACKAGES:
        package_dir = APP_ROOT / package
        assert package_dir.is_dir(), f"missing package dir: {package_dir}"
        for path in package_dir.rglob("*.py"):
            if path.name == "__init__.py" and path.stat().st_size == 0:
                continue
            violations.extend(_violations_in_file(path, package))

    assert not violations, "Import boundary violations:\n" + "\n".join(violations)
