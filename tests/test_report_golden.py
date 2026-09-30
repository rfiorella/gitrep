"""Golden output snapshots for report rendering (TEST_CHANGE_PROPOSALS T5).

Regenerate only when an output change is intended: run this module with
``GITREP_REGEN_GOLDEN=1``.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from rich.console import Console
from rich.table import Table

from gitrep.inspect import RepoStatus
from gitrep.report import render_json, render_table

DATA = Path(__file__).parent / "data"


def _mk(path, **kw) -> RepoStatus:
    base = {
        "path": Path(path),
        "branch": "main",
        "detached": False,
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "has_upstream": True,
        "stash_count": 0,
        "bare": False,
        "error": None,
        "remote_count": 1,
    }
    base.update(kw)
    return RepoStatus(**base)


ITEMS = [
    _mk("/root/clean"),
    _mk(
        "/root/dirty",
        dirty=True,
        ahead=2,
        stash_count=1,
        remote_count=2,
        upstream_master_ahead=2,
        upstream_master_behind=0,
    ),
    _mk(
        "/root/behind",
        behind=3,
        upstream_master_ahead=0,
        upstream_master_behind=3,
        upstream_same_name_ahead=0,
        upstream_same_name_behind=3,
    ),
    _mk("/root/broken", branch=None, error="fatal: bad", remote_count=0),
    _mk(
        "/root/detached",
        branch="abc1234",
        detached=True,
        has_upstream=False,
        stash_count=2,
    ),
]


def _plain(table: Table) -> str:
    c = Console(file=io.StringIO(), width=120, force_terminal=False)
    c.print(table)
    return c.file.getvalue()


def _markup(table: Table) -> str:
    """Header plus raw cell markup per row, so color changes are caught too."""
    cols = [list(col.cells) for col in table.columns]
    lines = [" | ".join(str(col.header) for col in table.columns)]
    lines += [" | ".join(str(col[i]) for col in cols) for i in range(table.row_count)]
    return "\n".join(lines) + "\n"


CASES = {
    "table_default.txt": lambda: _plain(render_table(ITEMS)),
    "table_full.txt": lambda: _plain(
        render_table(
            ITEMS, show_all=True, root="/root", show_upstream=True, show_remote=True
        )
    ),
    "table_full_markup.txt": lambda: _markup(
        render_table(
            ITEMS, show_all=True, root="/root", show_upstream=True, show_remote=True
        )
    ),
    "json_default.json": lambda: render_json(ITEMS) + "\n",
    "json_full.json": lambda: (
        render_json(ITEMS, show_all=True, show_upstream=True, show_remote=True) + "\n"
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden(name):
    actual = CASES[name]()
    golden = DATA / name
    if os.environ.get("GITREP_REGEN_GOLDEN"):
        golden.write_text(actual, encoding="utf-8")
    assert actual == golden.read_text(encoding="utf-8")
