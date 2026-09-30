from __future__ import annotations

import os
from pathlib import Path


def discover_repos(root: Path | str, *, skip_submodules: bool = True) -> list[Path]:
    """Walk ``root`` and return, sorted, the dirs that contain a ``.git`` directory.

    With ``skip_submodules=False``, dirs whose ``.git`` is a file (gitlink) are
    returned too. The walk never descends into a returned dir, so submodules
    inside a repo's worktree are not found.
    """
    found: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(Path(root).resolve()):
        cur = Path(dirpath)
        git = cur / ".git"
        if git.is_dir() or (not skip_submodules and git.is_file()):
            found.append(cur)
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames if d != ".git"]
    return sorted(found)
