from __future__ import annotations

import json
from pathlib import Path

from gitrep.inspect import RepoStatus
from gitrep.report import filter_attention, render_json, render_table


def _mk(path="/x", **kw):
    base = {
        "path":Path(path),
        "branch":"main",
        "detached":False,
        "dirty":False,
        "ahead":0,
        "behind":0,
        "has_upstream":True,
        "stash_count":0,
        "bare":False,
        "error":None,
    }
    base.update(kw)
    return RepoStatus(**base)


def test_filter_excludes_clean():
    clean = _mk("/clean")
    dirty = _mk("/dirty", dirty=True)
    behind = _mk("/behind", behind=2)
    stash = _mk("/stash", stash_count=1)
    err = _mk("/err", error="boom")
    out = filter_attention([clean, dirty, behind, stash, err])
    paths = [s.path for s in out]
    from pathlib import Path

    assert Path("/clean") not in paths
    for p in ("/dirty", "/behind", "/stash", "/err"):
        assert Path(p) in paths


def test_render_table_default_filters_clean():
    clean = _mk("/clean")
    dirty = _mk("/dirty", dirty=True)
    t = render_table([clean, dirty])
    # rich Table doesn't expose rows directly; use console capture
    import io

    from rich.console import Console

    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "/dirty" in out
    assert "/clean" not in out


def test_render_table_show_all_includes_clean():
    clean = _mk("/clean")
    dirty = _mk("/dirty", dirty=True)
    t = render_table([clean, dirty], show_all=True)
    import io

    from rich.console import Console

    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "/clean" in out
    assert "/dirty" in out


def test_render_json_round_trip():
    items = [_mk("/a", dirty=True), _mk("/b", behind=3, ahead=1)]
    s = render_json(items)
    parsed = json.loads(s)
    assert isinstance(parsed, list) and len(parsed) == 2
    assert parsed[0]["path"] == "/a"
    assert parsed[0]["dirty"] is True
    assert parsed[1]["behind"] == 3
    assert parsed[1]["ahead"] == 1


def test_render_json_default_filters_clean():
    items = [_mk("/clean"), _mk("/dirty", dirty=True)]
    parsed = json.loads(render_json(items))
    assert [p["path"] for p in parsed] == ["/dirty"]


def test_render_json_show_all_includes_clean():
    items = [_mk("/clean"), _mk("/dirty", dirty=True)]
    parsed = json.loads(render_json(items, show_all=True))
    assert sorted(p["path"] for p in parsed) == ["/clean", "/dirty"]


# --- upstream-status rendering -------------------------------------------


def test_upstream_master_render_table_shows_columns_when_flag_set():
    item = _mk(
        "/u",
        dirty=True,
        upstream_master_ahead=2,
        upstream_master_behind=1,
        upstream_same_name_ahead=0,
        upstream_same_name_behind=0,
    )
    t = render_table([item], show_upstream=True)
    import io

    from rich.console import Console

    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "vs master (A/B)" in out
    assert "vs same-name (A/B)" in out
    assert "2/1" in out
    assert "0/0" in out


def test_upstream_same_name_render_table_blank_when_missing():
    item = _mk(
        "/u",
        dirty=True,
        upstream_master_ahead=1,
        upstream_master_behind=0,
        upstream_same_name_ahead=None,
        upstream_same_name_behind=None,
    )
    t = render_table([item], show_upstream=True)
    import io

    from rich.console import Console

    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "1/0" in out
    # The same-name cell must NOT render "None"; it should be empty.
    assert "None" not in out


def test_upstream_missing_render_table_blank_for_all():
    item = _mk("/u", dirty=True)  # all four upstream fields default None
    t = render_table([item], show_upstream=True)
    import io

    from rich.console import Console

    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "None" not in out


def test_render_table_omits_upstream_columns_when_flag_unset():
    item = _mk(
        "/u",
        dirty=True,
        upstream_master_ahead=2,
        upstream_master_behind=1,
    )
    t = render_table([item])
    import io

    from rich.console import Console

    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "vs master" not in out
    assert "vs same-name" not in out


def test_upstream_master_render_json_includes_keys_when_flag_set():
    item = _mk(
        "/u",
        dirty=True,
        upstream_master_ahead=2,
        upstream_master_behind=1,
        upstream_same_name_ahead=0,
        upstream_same_name_behind=0,
    )
    parsed = json.loads(render_json([item], show_upstream=True))
    assert parsed[0]["upstream_master_ahead"] == 2
    assert parsed[0]["upstream_master_behind"] == 1
    assert parsed[0]["upstream_same_name_ahead"] == 0
    assert parsed[0]["upstream_same_name_behind"] == 0


def test_upstream_missing_render_json_serialises_null():
    item = _mk("/u", dirty=True)  # all four None
    parsed = json.loads(render_json([item], show_upstream=True))
    assert parsed[0]["upstream_master_ahead"] is None
    assert parsed[0]["upstream_same_name_ahead"] is None


def test_render_json_omits_upstream_keys_when_flag_unset():
    item = _mk(
        "/u",
        dirty=True,
        upstream_master_ahead=2,
        upstream_master_behind=1,
    )
    parsed = json.loads(render_json([item]))
    for k in (
        "upstream_master_ahead",
        "upstream_master_behind",
        "upstream_same_name_ahead",
        "upstream_same_name_behind",
    ):
        assert k not in parsed[0]


# --- remote-status rendering ----------------------------------------------

def test_render_table_shows_remotes_column_when_flag_set():
    item = _mk("/r", dirty=True, remote_count=3)
    t = render_table([item], show_remote=True)
    from rich.console import Console
    import io
    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "remotes" in out
    assert "3" in out


def test_render_table_omits_remotes_column_when_flag_unset():
    item = _mk("/r", dirty=True, remote_count=3)
    t = render_table([item])
    from rich.console import Console
    import io
    c = Console(file=io.StringIO(), width=200, force_terminal=False)
    c.print(t)
    out = c.file.getvalue()
    assert "remotes" not in out


def test_render_json_includes_remote_count_when_flag_set():
    item = _mk("/r", dirty=True, remote_count=4)
    parsed = json.loads(render_json([item], show_remote=True))
    assert parsed[0]["remote_count"] == 4


def test_render_json_omits_remote_count_when_flag_unset():
    item = _mk("/r", dirty=True, remote_count=4)
    parsed = json.loads(render_json([item]))
    assert "remote_count" not in parsed[0]
