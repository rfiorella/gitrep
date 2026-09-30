"""Characterization tests for table notes and paths (TEST_CHANGE_PROPOSALS T4)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console
from rich.table import Table

from gitrep.inspect import RepoStatus
from gitrep.report import render_table


def _mk(path="/x", **kw) -> RepoStatus:
    base = {
        "path": Path(path),
        "branch": "main",
        "detached": False,
        "dirty": True,
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


def _render(table: Table) -> str:
    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(table)
    return c.file.getvalue()


def _row(out: str, needle: str) -> str:
    return next(ln for ln in out.splitlines() if needle in ln)


@pytest.mark.parametrize(
    ("kw", "note"),
    [
        ({"error": "boom"}, "error: boom"),
        ({"error": "boom", "has_upstream": False, "detached": True}, "error: boom"),
        ({"has_upstream": False}, "no upstream"),
        ({"has_upstream": False, "detached": True}, "detached"),
        ({"detached": True}, "detached"),
        ({"detached": True, "bare": True}, "detached"),
        ({"has_upstream": False, "bare": True}, "bare"),
        ({"bare": True}, "bare"),
    ],
)
def test_note_precedence(kw, note):
    out = _render(render_table([_mk("/repo", **kw)]))
    row = _row(out, "/repo")
    assert row.rstrip(" │").endswith(note)
    others = {"error: boom", "no upstream", "detached", "bare"} - {note}
    for other in others:
        assert other not in row


def test_note_empty_when_healthy():
    out = _render(render_table([_mk("/repo")]))
    cells = [c.strip() for c in _row(out, "/repo").split("│")]
    assert cells[-2] == ""


def test_branch_none_renders_dash():
    out = _render(render_table([_mk("/repo", branch=None)]))
    cells = [c.strip() for c in _row(out, "/repo").split("│")]
    assert cells[2] == "-"


def test_root_makes_paths_relative_and_titles_table():
    items = [_mk("/nonexistent-root/sub/x"), _mk("/elsewhere/y")]
    out = _render(render_table(items, root="/nonexistent-root"))
    assert "gitrep (2/2 shown) — /nonexistent-root" in out
    assert "│ sub/x " in out
    assert "/nonexistent-root/sub/x" not in out
    assert "│ /elsewhere/y " in out


def test_title_without_root():
    out = _render(render_table([_mk("/a"), _mk("/b", dirty=False)]))
    assert "gitrep (1/2 shown)" in out
    assert "—" not in out
