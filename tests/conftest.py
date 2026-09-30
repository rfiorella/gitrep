from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(
    cwd: Path, *args: str, env_extra: dict | None = None
) -> subprocess.CompletedProcess:
    env = {**os.environ, **_GIT_ENV}
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {args} failed in {cwd}: {proc.stderr}")
    return proc


def _init_repo(path: Path, *, initial_branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", initial_branch)
    _git(path, "config", "commit.gpgsign", "false")
    return path


def _commit(repo: Path, name: str, content: str = "x", message: str = "msg") -> None:
    f = repo / name
    f.write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def make_repo(tmp_path):
    def _factory(name: str, *, initial_branch: str = "main") -> Path:
        return _init_repo(tmp_path / name, initial_branch=initial_branch)

    return _factory


@pytest.fixture
def git():
    return _git


@pytest.fixture
def commit():
    return _commit


@pytest.fixture
def repo_tree(tmp_path):
    """Build a tree of repos for discovery + integration tests."""
    root = tmp_path / "code"
    root.mkdir()
    # plain repo
    a = _init_repo(root / "a")
    _commit(a, "f.txt")
    # nested sibling under subdir
    b = _init_repo(root / "nested" / "b")
    _commit(b, "f.txt")
    # repo at deeper depth
    c = _init_repo(root / "nested" / "deep" / "c")
    _commit(c, "f.txt")
    # submodule-style: a directory containing a `.git` *file* (gitlink),
    # placed in its own subtree so the repo-pruning of a parent worktree
    # doesn't hide it from the discovery walk.
    sub = root / "submod_holder" / "submod"
    sub.mkdir(parents=True)
    (sub / ".git").write_text("gitdir: ../../.gitmodules-fake\n")
    # also a parent dir with its own real repo to exercise pruning
    parent = _init_repo(root / "with_sub")
    _commit(parent, "f.txt")
    # noise: non-repo dir
    (root / "notrepo").mkdir()
    (root / "notrepo" / "file.txt").write_text("hi")
    return root


@pytest.fixture
def clone_pair(make_repo):
    """Factory for an ``(upstream, work)`` pair; ``work`` tracks ``origin/<branch>``.

    ``upstream`` has two commits. With ``set_origin_head=True``,
    ``refs/remotes/origin/HEAD`` in ``work`` is pointed at ``origin/<branch>``.
    """

    def _factory(
        name: str, *, branch: str = "main", set_origin_head: bool = False
    ) -> tuple[Path, Path]:
        upstream = make_repo(f"{name}-up", initial_branch=branch)
        _commit(upstream, "f.txt")
        _commit(upstream, "g.txt")
        work = make_repo(name, initial_branch=branch)
        _git(work, "remote", "add", "origin", str(upstream))
        _git(work, "fetch", "-q", "origin")
        _git(work, "checkout", "-q", "-B", branch, f"origin/{branch}")
        _git(work, "branch", f"--set-upstream-to=origin/{branch}", branch)
        if set_origin_head:
            _git(
                work,
                "symbolic-ref",
                "refs/remotes/origin/HEAD",
                f"refs/remotes/origin/{branch}",
            )
        return upstream, work

    return _factory
