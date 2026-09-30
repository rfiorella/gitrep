from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_UPSTREAM_FIELDS = (
    "upstream_master_ahead",
    "upstream_master_behind",
    "upstream_same_name_ahead",
    "upstream_same_name_behind",
)


@dataclass
class RepoStatus:
    path: Path
    branch: str | None
    detached: bool
    dirty: bool
    ahead: int
    behind: int
    has_upstream: bool
    stash_count: int
    bare: bool
    error: str | None
    remote_count: int
    upstream_master_ahead: int | None = None
    upstream_master_behind: int | None = None
    upstream_same_name_ahead: int | None = None
    upstream_same_name_behind: int | None = None

    def to_dict(
        self, *, include_upstream: bool = False, include_remote: bool = False
    ) -> dict[str, Any]:
        """JSON-ready dict; upstream and remote fields only when requested."""
        d = asdict(self)
        d["path"] = str(self.path)
        if not include_upstream:
            for k in _UPSTREAM_FIELDS:
                del d[k]
        if not include_remote:
            del d["remote_count"]
        return d

    @property
    def needs_attention(self) -> bool:
        """True if the repo errored, is dirty, is behind, or has stashes."""
        return bool(self.error or self.dirty or self.behind or self.stash_count)


def _run(path: Path, args: list[str], timeout: float) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _left_right_counts(path: Path, ref: str, timeout: float) -> tuple[int, int] | None:
    """Return ``(ahead, behind)`` of HEAD relative to ``ref``.

    Returns None if git fails or prints other than two tokens; raises
    ValueError if the tokens are not integers.
    """
    rc, out, _ = _run(
        path, ["rev-list", "--left-right", "--count", f"{ref}...HEAD"], timeout
    )
    if rc != 0:
        return None
    parts = out.split()
    if len(parts) != 2:
        return None
    behind, ahead = int(parts[0]), int(parts[1])
    return ahead, behind


def _count_lines(out: str) -> int:
    return sum(1 for line in out.splitlines() if line.strip())


def upstream_status(
    path: Path | str,
    *,
    branch: str | None,
    timeout: float = 5.0,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Return (master_ahead, master_behind, same_name_ahead, same_name_behind).

    Each pair is ``(None, None)`` when the corresponding upstream ref cannot
    be resolved (no ``origin``, ``origin/HEAD`` not configured, no current
    branch, same-name branch missing on origin, etc.). Errors are swallowed
    and reported as ``None`` so the caller can render blank cells.
    """
    path = Path(path)
    master: tuple[int | None, int | None] = (None, None)
    same: tuple[int | None, int | None] = (None, None)

    def _pair(ref: str) -> tuple[int | None, int | None]:
        try:
            return _left_right_counts(path, ref, timeout) or (None, None)
        except ValueError:
            return (None, None)

    try:
        rc, out, _ = _run(path, ["rev-parse", "--abbrev-ref", "origin/HEAD"], timeout)
        if rc == 0:
            master_ref = out.strip()
            # A non-symbolic origin/HEAD abbreviates to itself.
            if master_ref and master_ref != "origin/HEAD":
                master = _pair(master_ref)

        if branch:
            rc, _, _ = _run(
                path,
                ["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
                timeout,
            )
            if rc == 0:
                same = _pair(f"origin/{branch}")
    except (subprocess.TimeoutExpired, OSError, UnicodeDecodeError):
        pass

    return (*master, *same)


def inspect_repo(
    path: Path | str,
    *,
    timeout: float = 5.0,
    with_upstream: bool = False,
) -> RepoStatus:
    """Inspect a single repo and return its status.

    ``timeout`` applies to each git command, not to the whole inspection.
    Git failures are recorded in ``error`` rather than raised.

    When ``with_upstream`` is True, additionally populate
    ``upstream_master_*`` and ``upstream_same_name_*`` fields by querying
    ``origin/HEAD`` and ``origin/<branch>``. Detached HEAD or any failure
    leaves the corresponding fields as None.
    """
    path = Path(path)
    status = RepoStatus(
        path=path,
        branch=None,
        detached=False,
        dirty=False,
        ahead=0,
        behind=0,
        has_upstream=False,
        stash_count=0,
        bare=False,
        error=None,
        remote_count=0,
    )

    try:
        rc, out, err = _run(path, ["rev-parse", "--is-bare-repository"], timeout)
        if rc != 0:
            status.error = err.strip() or out.strip() or "git rev-parse failed"
            return status
        status.bare = out.strip() == "true"

        rc, out, _ = _run(path, ["remote"], timeout)
        if rc == 0:
            status.remote_count = _count_lines(out)

        rc, out, _ = _run(path, ["rev-parse", "--abbrev-ref", "HEAD"], timeout)
        if rc == 0:
            ref = out.strip()
            if ref == "HEAD":
                status.detached = True
                rc, out, _ = _run(path, ["rev-parse", "--short", "HEAD"], timeout)
                status.branch = out.strip() if rc == 0 else None
            else:
                status.branch = ref or None

        if not status.bare:
            rc, out, _ = _run(path, ["status", "--porcelain"], timeout)
            if rc == 0:
                status.dirty = bool(out.strip())

        if status.branch and not status.detached:
            rc, _, _ = _run(
                path,
                ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                timeout,
            )
            status.has_upstream = rc == 0
            if status.has_upstream:
                counts = _left_right_counts(path, "@{u}", timeout)
                if counts is not None:
                    status.ahead, status.behind = counts

        rc, out, _ = _run(path, ["stash", "list"], timeout)
        if rc == 0:
            status.stash_count = _count_lines(out)

        if with_upstream and not status.bare:
            # When detached, ``branch`` holds a short SHA, not a branch name.
            branch = None if status.detached else status.branch
            (
                status.upstream_master_ahead,
                status.upstream_master_behind,
                status.upstream_same_name_ahead,
                status.upstream_same_name_behind,
            ) = upstream_status(path, branch=branch, timeout=timeout)

    except subprocess.TimeoutExpired:
        status.error = f"timeout after {timeout}s"
    except FileNotFoundError as e:
        status.error = f"git not found: {e}"
    except (OSError, UnicodeDecodeError) as e:
        status.error = f"{type(e).__name__}: {e}"

    return status
