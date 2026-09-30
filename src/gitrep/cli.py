from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from .discovery import discover_repos
from .fetch import fetch_all
from .inspect import RepoStatus, inspect_repo
from .report import render_json, render_table


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitrep", description="Multi-repo status & mass-fetch manager"
    )
    p.add_argument("--root", default="/code", help="Root dir to scan (default: /code)")
    p.add_argument(
        "--all", action="store_true", help="Show all repos, not just attention-needing"
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of table")
    p.add_argument("--no-fetch", action="store_true", help="Skip parallel fetch step")
    p.add_argument(
        "--workers", type=int, default=16, help="Fetch worker count (default 16)"
    )
    p.add_argument(
        "--fetch-timeout",
        type=float,
        default=30.0,
        help="Per-repo fetch timeout seconds",
    )
    p.add_argument(
        "--inspect-timeout",
        type=float,
        default=10.0,
        help="Per-repo inspect timeout seconds",
    )
    p.add_argument(
        "--include-submodules",
        action="store_true",
        help="Include submodule .git-file repos",
    )
    p.add_argument(
        "--pull-clean",
        action="store_true",
        help="After listing, prompt to pull repos that are clean and behind",
    )
    p.add_argument(
        "--show-diff",
        action="store_true",
        help="Print git status -s for each dirty repo",
    )
    p.add_argument(
        "--upstream-status",
        action="store_true",
        help=(
            "Also report ahead/behind vs origin/HEAD (upstream master) and "
            "vs origin/<current-branch> (same-name)."
        ),
    )
    p.add_argument(
        "--remote-status",
        action="store_true",
        help="Also report the number of configured remotes per repo.",
    )
    return p


def _pull_clean_base_eligible(s: RepoStatus) -> bool:
    """Every ``--pull-clean`` condition except the remote-count restriction."""
    return (
        bool(s.behind)
        and not s.dirty
        and not s.detached
        and s.has_upstream
        and not s.error
    )


def _confirm(prompt: str) -> bool:
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in {"y", "yes"}


def _render(
    console: Console, statuses: list[RepoStatus], args: argparse.Namespace, root: Path
) -> None:
    if args.json:
        # Plain print: rich markup/highlighting must not touch the JSON.
        print(
            render_json(
                statuses,
                show_all=args.all,
                show_upstream=args.upstream_status,
                show_remote=args.remote_status,
            )
        )
    else:
        console.print(
            render_table(
                statuses,
                show_all=args.all,
                root=str(root),
                show_upstream=args.upstream_status,
                show_remote=args.remote_status,
            )
        )


def _show_diff(console: Console, statuses: list[RepoStatus]) -> None:
    for s in statuses:
        if s.dirty:
            console.rule(str(s.path))
            subprocess.run(["git", "-C", str(s.path), "status", "-s"], check=False)


def _pull_clean(console: Console, statuses: list[RepoStatus]) -> None:
    """List eligible repos, then ``pull --ff-only`` them after confirmation.

    Repos with more than one remote are skipped: which remote to pull from
    is ambiguous.
    """
    eligible = [s for s in statuses if _pull_clean_base_eligible(s)]
    targets = [s for s in eligible if s.remote_count == 1]
    skipped = [s for s in eligible if s.remote_count != 1]

    if targets:
        console.print(f"[bold]pull-clean targets ({len(targets)}):[/bold]")
        for s in targets:
            console.print(f"  {s.path} (behind {s.behind})")
    else:
        console.print("[dim]no clean+behind repos to pull[/dim]")

    if skipped:
        console.print(
            f"[dim]skipped {len(skipped)} repo(s) with multiple remotes:[/dim]"
        )
        for s in skipped:
            console.print(f"  {s.path} ({s.remote_count} remotes)")

    if not targets:
        return
    if not _confirm("proceed with pull on these repos? [y/N] "):
        console.print("[dim]aborted[/dim]")
        return
    for s in targets:
        console.rule(str(s.path))
        subprocess.run(["git", "-C", str(s.path), "pull", "--ff-only"], check=False)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    console = Console()

    root = Path(args.root)
    if not root.exists():
        console.print(f"[red]root not found: {root}[/red]")
        return 2

    repos = discover_repos(root, skip_submodules=not args.include_submodules)
    if not repos:
        console.print(f"[yellow]no repos found under {root}[/yellow]")
        return 0

    if not args.no_fetch:
        with console.status(f"fetching {len(repos)} repos…"):
            fetch_all(repos, max_workers=args.workers, timeout=args.fetch_timeout)

    statuses = [
        inspect_repo(
            p, timeout=args.inspect_timeout, with_upstream=args.upstream_status
        )
        for p in repos
    ]

    _render(console, statuses, args, root)
    if args.show_diff:
        _show_diff(console, statuses)
    if args.pull_clean:
        _pull_clean(console, statuses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
