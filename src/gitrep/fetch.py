from __future__ import annotations

import subprocess
import time
from concurrent.futures import (
    BrokenExecutor,
    CancelledError,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FetchResult:
    ok: bool
    stderr: str
    duration_s: float


def _fetch_one(path: Path, timeout: float) -> FetchResult:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "fetch", "--all", "--prune", "--quiet"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        dur = time.monotonic() - t0
        return FetchResult(
            ok=(proc.returncode == 0),
            stderr=proc.stderr.strip(),
            duration_s=dur,
        )
    except subprocess.TimeoutExpired:
        return FetchResult(
            ok=False,
            stderr=f"timeout after {timeout}s",
            duration_s=time.monotonic() - t0,
        )
    except FileNotFoundError as e:
        return FetchResult(
            ok=False, stderr=f"git not found: {e}", duration_s=time.monotonic() - t0
        )
    except (OSError, UnicodeDecodeError) as e:
        return FetchResult(
            ok=False,
            stderr=f"{type(e).__name__}: {e}",
            duration_s=time.monotonic() - t0,
        )


def fetch_all(
    repos: list[Path],
    *,
    max_workers: int = 16,
    timeout: float = 30.0,
) -> dict[Path, FetchResult]:
    """Fetch all repos in parallel; never abort batch on individual failures."""
    if not repos:
        return {}
    results: dict[Path, FetchResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(repos)))) as ex:
        futures = {ex.submit(_fetch_one, p, timeout): p for p in repos}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                results[p] = fut.result()
            except (CancelledError, BrokenExecutor) as e:
                results[p] = FetchResult(
                    ok=False, stderr=f"{type(e).__name__}: {e}", duration_s=0.0
                )
    return results
