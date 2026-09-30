"""Helpers shared by modules that shell out to git."""

from __future__ import annotations

import subprocess
from pathlib import Path

# Failures of a single git invocation that are reported per repo, not raised.
GIT_ERRORS = (subprocess.TimeoutExpired, OSError, UnicodeDecodeError)


def git_argv(path: Path | str, *args: str) -> list[str]:
    return ["git", "-C", str(path), *args]


def describe_error(exc: Exception, timeout: float) -> str:
    """One-line message for an exception from ``GIT_ERRORS``."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"timeout after {timeout}s"
    if isinstance(exc, FileNotFoundError):
        return f"git not found: {exc}"
    return f"{type(exc).__name__}: {exc}"
