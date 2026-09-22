from __future__ import annotations

import json
from collections.abc import Iterable

from rich.table import Table

from .inspect import RepoStatus


def filter_attention(statuses: Iterable[RepoStatus]) -> list[RepoStatus]:
    return [s for s in statuses if s.needs_attention]


def _ab_cell(ahead: int | None, behind: int | None) -> str:
    if ahead is None or behind is None:
        return ""
    return f"{ahead}/{behind}"


def render_table(
    statuses: list[RepoStatus],
    *,
    show_all: bool = False,
    root: str | None = None,
    show_upstream: bool = False,
    show_remote: bool = False,
) -> Table:
    rows = list(statuses) if show_all else filter_attention(statuses)

    title = f"gitrep ({len(rows)}/{len(statuses)} shown)"
    if root:
        title = f"{title} — {root}"
    table = Table(title=title, show_lines=False, expand=False)
    table.add_column("repo", overflow="fold", no_wrap=False)
    table.add_column("branch")
    table.add_column("dirty", justify="center")
    table.add_column("ahead", justify="right")
    table.add_column("behind", justify="right")
    table.add_column("stash", justify="right")
    if show_remote:
        table.add_column("remotes", justify="right")
    if show_upstream:
        table.add_column("vs master (A/B)", justify="right")
        table.add_column("vs same-name (A/B)", justify="right")
    table.add_column("note")

    for s in rows:
        if s.error:
            note = f"[red]error: {s.error}[/red]"
        elif not s.has_upstream and not s.detached and not s.bare:
            note = "[yellow]no upstream[/yellow]"
        elif s.detached:
            note = "[yellow]detached[/yellow]"
        elif s.bare:
            note = "[dim]bare[/dim]"
        else:
            note = ""

        repo_str = str(s.path) if root is None else _relpath(s.path, root)
        branch = s.branch or "-"
        dirty_cell = "[red]*[/red]" if s.dirty else ""
        ahead_cell = f"[green]{s.ahead}[/green]" if s.ahead else "0"
        behind_cell = f"[yellow]{s.behind}[/yellow]" if s.behind else "0"
        stash_cell = f"[cyan]{s.stash_count}[/cyan]" if s.stash_count else "0"

        cells = [repo_str, branch, dirty_cell, ahead_cell, behind_cell, stash_cell]
        if show_remote:
            cells.append(str(s.remote_count))
        if show_upstream:
            cells.append(_ab_cell(s.upstream_master_ahead, s.upstream_master_behind))
            cells.append(
                _ab_cell(s.upstream_same_name_ahead, s.upstream_same_name_behind)
            )
        cells.append(note)
        table.add_row(*cells)

    return table


def _relpath(p, root: str) -> str:
    try:
        from pathlib import Path

        return str(Path(p).resolve().relative_to(Path(root).resolve()))
    except (ValueError, OSError):
        return str(p)


def render_json(
    statuses: list[RepoStatus],
    *,
    show_all: bool = False,
    show_upstream: bool = False,
    show_remote: bool = False,
) -> str:
    rows = list(statuses) if show_all else filter_attention(statuses)
    return json.dumps(
        [s.to_dict(include_remote=show_remote, include_upstream=show_upstream) for s in rows],
        indent=2,
        sort_keys=True,
    )
