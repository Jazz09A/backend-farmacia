#!/usr/bin/env python3
"""Dependency parity gate between pyproject.toml and requirements.txt.

WHY this exists
---------------
``pyproject.toml`` is the source of truth for dependencies, but the production
deploy job (``.github/workflows/deploy-backend.yml``) installs with
``pip install -r requirements.txt``. That file is maintained by hand, so it can
silently drift. The drift already happened: ``redis`` and ``orjson`` were
missing from ``requirements.txt``, so production ran without Redis and the
cache silently degraded to an in-memory fallback while CI stayed green.

This script fails (exit 1) whenever the two files disagree on package names,
so that drift cannot reach production again. It is stdlib-only on purpose: the
CI step runs BEFORE any dependency is installed.

Scope note: ``requirements.txt`` mirrors only the runtime dependencies
(``project.dependencies``). The ``dev``/``test`` extras are deliberately NOT
compared, because CI installs them separately via ``pip install -e ".[dev,test]"``.
"""

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"


def normalize(name: str) -> str:
    """PEP 503 normalization: lowercase and collapse ``-``/``_``/``.`` into ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    """Extract the bare package name from a requirement string.

    Handles extras (``pyjwt[crypto]`` -> ``pyjwt``), version specifiers
    (``redis>=5.0.1`` -> ``redis``), environment markers (``foo; python_version<"3.12"``)
    and inline comments (``foo>=1.0  # pin``).
    """
    text = requirement.split("#", 1)[0].split(";", 1)[0].strip()
    match = re.match(r"^[A-Za-z0-9._-]+", text)
    return normalize(match.group(0)) if match else ""


def names_from_requirements(text: str) -> set[str]:
    """Collect normalized package names from a requirements-style file."""
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = requirement_name(stripped)
        if name:
            names.add(name)
    return names


def main() -> int:
    project = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8")).get("project", {})

    runtime = {requirement_name(dep) for dep in project.get("dependencies", [])}
    runtime.discard("")

    # Loaded for visibility only: extras are installed separately in CI.
    extras = project.get("optional-dependencies", {})
    excluded = [requirement_name(dep) for group in ("dev", "test") for dep in extras.get(group, [])]
    print(f"info: extras excluded from comparison: {', '.join(sorted(excluded)) or 'none'}")

    installed = names_from_requirements(REQUIREMENTS_PATH.read_text(encoding="utf-8"))

    missing = sorted(runtime - installed)
    extra = sorted(installed - runtime)

    if missing or extra:
        if missing:
            print(f"FAIL: missing from {REQUIREMENTS_PATH.name}: {', '.join(missing)}")
        if extra:
            print(f"FAIL: not declared in pyproject.toml: {', '.join(extra)}")
        return 1

    print(f"OK: {REQUIREMENTS_PATH.name} matches pyproject.toml ({len(runtime)} runtime dependencies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
