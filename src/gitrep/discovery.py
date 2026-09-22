from __future__ import annotations

import os
from pathlib import Path


def _is_repo_root(p: Path) -> bool:
    git = p / ".git"
    if git.is_dir():
        return True
    if git.is_file():
        return False
    return False


def _is_submodule_marker(p: Path) -> bool:
    git = p / ".git"
    return git.is_file()


def discover_repos(root: Path | str, *, skip_submodules: bool = True) -> list[Path]:
    """Walk root and return repo paths (dirs containing a .git directory)."""
    root = Path(root).resolve()
    found: list[Path] = []
    if not root.exists():
        return found

    for dirpath, dirnames, _filenames in os.walk(
        root, followlinks=False, onerror=lambda _e: None
    ):
        cur = Path(dirpath)
        if _is_repo_root(cur):
            found.append(cur)
            dirnames[:] = []
            continue
        if not skip_submodules and _is_submodule_marker(cur):
            found.append(cur)
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in {".git"}]

    return sorted(found)
