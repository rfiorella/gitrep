from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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

    def to_dict(self, *, include_upstream: bool = False, include_remote: bool = False) -> dict[str, Any]:
        d = asdict(self)
        d["path"] = str(self.path)
        if not include_upstream:
            for k in (
                "upstream_master_ahead",
                "upstream_master_behind",
                "upstream_same_name_ahead",
                "upstream_same_name_behind",
            ):
                d.pop(k, None)
        if not include_remote:
            d.pop("remote_count", None)
        return d

    @property
    def needs_attention(self) -> bool:
        return bool(self.error or self.dirty or self.behind or self.stash_count)


def _run(path: Path, args: list[str], timeout: float) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


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

    master_ahead: int | None = None
    master_behind: int | None = None
    same_ahead: int | None = None
    same_behind: int | None = None

    def _ab(ref: str) -> tuple[int | None, int | None]:
        rc, out, _ = _run(
            path, ["rev-list", "--left-right", "--count", f"{ref}...HEAD"], timeout
        )
        if rc != 0:
            return (None, None)
        parts = out.split()
        if len(parts) != 2:
            return (None, None)
        try:
            behind_n = int(parts[0])
            ahead_n = int(parts[1])
        except ValueError:
            return (None, None)
        return (ahead_n, behind_n)

    try:
        # Upstream master via origin/HEAD symbolic ref.
        rc, out, _ = _run(path, ["rev-parse", "--abbrev-ref", "origin/HEAD"], timeout)
        if rc == 0:
            master_ref = out.strip()
            if master_ref and master_ref != "origin/HEAD":
                master_ahead, master_behind = _ab(master_ref)

        # Same-name branch on origin (only if we have a non-detached branch).
        if branch:
            rc, _out, _ = _run(
                path,
                ["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
                timeout,
            )
            if rc == 0:
                same_ahead, same_behind = _ab(f"origin/{branch}")
    except subprocess.TimeoutExpired:
        # leave any unresolved fields as None
        pass
    except (OSError, UnicodeDecodeError):
        pass

    return (master_ahead, master_behind, same_ahead, same_behind)


def inspect_repo(
    path: Path | str,
    *,
    timeout: float = 5.0,
    with_upstream: bool = False,
) -> RepoStatus:
    """Inspect a single repo and return its status.

    When ``with_upstream`` is True, additionally populate
    ``upstream_master_*`` and ``upstream_same_name_*`` fields by querying
    ``origin/HEAD`` and ``origin/<branch>``. Detached HEAD or any failure
    leaves the corresponding fields as None.
    """
    path = Path(path)
    base = RepoStatus(
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
            base.error = err.strip() or out.strip() or "git rev-parse failed"
            return base
        base.bare = out.strip() == "true"

        rc, out, _ = _run(path, ["remote"], timeout)
        if rc == 0:
            base.remote_count = sum(1 for line in out.splitlines() if line.strip())

        rc, out, _ = _run(path, ["rev-parse", "--abbrev-ref", "HEAD"], timeout)
        if rc == 0:
            ref = out.strip()
            if ref == "HEAD":
                base.detached = True
                rc2, out2, _ = _run(path, ["rev-parse", "--short", "HEAD"], timeout)
                base.branch = out2.strip() if rc2 == 0 else None
            else:
                base.branch = ref or None

        if not base.bare:
            rc, out, _ = _run(path, ["status", "--porcelain"], timeout)
            if rc == 0:
                base.dirty = bool(out.strip())

        if base.branch and not base.detached:
            rc, _out, _err = _run(
                path,
                ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                timeout,
            )
            base.has_upstream = rc == 0
            if base.has_upstream:
                rc, out, _ = _run(
                    path,
                    ["rev-list", "--left-right", "--count", "@{u}...HEAD"],
                    timeout,
                )
                if rc == 0:
                    parts = out.split()
                    if len(parts) == 2:
                        base.behind = int(parts[0])
                        base.ahead = int(parts[1])

        rc, out, _ = _run(path, ["stash", "list"], timeout)
        if rc == 0:
            base.stash_count = sum(1 for line in out.splitlines() if line.strip())

        if with_upstream and not base.bare:
            # Detached HEAD -> branch is the short SHA, not a real branch
            # name; pass None for the branch arg so same-name lookup is
            # skipped.
            br = None if base.detached else base.branch
            ma, mb, sa, sb = upstream_status(path, branch=br, timeout=timeout)
            base.upstream_master_ahead = ma
            base.upstream_master_behind = mb
            base.upstream_same_name_ahead = sa
            base.upstream_same_name_behind = sb

    except subprocess.TimeoutExpired:
        base.error = f"timeout after {timeout}s"
    except FileNotFoundError as e:
        base.error = f"git not found: {e}"
    except (OSError, UnicodeDecodeError) as e:
        base.error = f"{type(e).__name__}: {e}"

    return base
