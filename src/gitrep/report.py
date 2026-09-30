from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from rich.table import Table

from .inspect import RepoStatus


def filter_attention(statuses: Iterable[RepoStatus]) -> list[RepoStatus]:
    """Keep only statuses where ``needs_attention`` is true."""
    return [s for s in statuses if s.needs_attention]


def _select(statuses: list[RepoStatus], show_all: bool) -> list[RepoStatus]:
    return list(statuses) if show_all else filter_attention(statuses)


def _ab_cell(ahead: int | None, behind: int | None) -> str:
    if ahead is None or behind is None:
        return ""
    return f"{ahead}/{behind}"


def _count_cell(n: int, color: str) -> str:
    return f"[{color}]{n}[/{color}]" if n else "0"


def _note(s: RepoStatus) -> str:
    if s.error:
        return f"[red]error: {s.error}[/red]"
    if not s.has_upstream and not s.detached and not s.bare:
        return "[yellow]no upstream[/yellow]"
    if s.detached:
        return "[yellow]detached[/yellow]"
    if s.bare:
        return "[dim]bare[/dim]"
    return ""


def render_table(
    statuses: list[RepoStatus],
    *,
    show_all: bool = False,
    root: str | None = None,
    show_upstream: bool = False,
    show_remote: bool = False,
) -> Table:
    """Build a rich table; paths are shown relative to ``root`` when given."""
    rows = _select(statuses, show_all)

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
        cells = [
            str(s.path) if root is None else _relpath(s.path, root),
            s.branch or "-",
            "[red]*[/red]" if s.dirty else "",
            _count_cell(s.ahead, "green"),
            _count_cell(s.behind, "yellow"),
            _count_cell(s.stash_count, "cyan"),
        ]
        if show_remote:
            cells.append(str(s.remote_count))
        if show_upstream:
            cells.append(_ab_cell(s.upstream_master_ahead, s.upstream_master_behind))
            cells.append(
                _ab_cell(s.upstream_same_name_ahead, s.upstream_same_name_behind)
            )
        cells.append(_note(s))
        table.add_row(*cells)

    return table


def _relpath(p: Path | str, root: str) -> str:
    try:
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
    """Serialize statuses as a sorted-key, indented JSON array."""
    return json.dumps(
        [
            s.to_dict(include_remote=show_remote, include_upstream=show_upstream)
            for s in _select(statuses, show_all)
        ],
        indent=2,
        sort_keys=True,
    )
