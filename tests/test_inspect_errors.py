"""Characterization tests for inspect error paths (TEST_CHANGE_PROPOSALS T2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gitrep import inspect as inspect_mod
from gitrep.inspect import inspect_repo, upstream_status


def _scripted(responses):
    """Fake ``_run`` answering by git argv; values are tuples or exceptions."""

    def _run(_path, args, _timeout):
        r = responses.get(tuple(args), (0, "", ""))
        if isinstance(r, BaseException):
            raise r
        return r

    return _run


BARE = ("rev-parse", "--is-bare-repository")
REMOTE = ("remote",)
HEAD = ("rev-parse", "--abbrev-ref", "HEAD")
UPSTREAM = ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
TRACKING = ("rev-list", "--left-right", "--count", "@{u}...HEAD")
ORIGIN_HEAD = ("rev-parse", "--abbrev-ref", "origin/HEAD")
MASTER_AB = ("rev-list", "--left-right", "--count", "origin/main...HEAD")
SAME_VERIFY = ("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main")
SAME_AB = ("rev-list", "--left-right", "--count", "origin/main...HEAD")


# --- inspect_repo ----------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (subprocess.TimeoutExpired(["git"], 99), "timeout after 2.0s"),
        (FileNotFoundError("git"), "git not found: git"),
        (OSError("boom"), "OSError: boom"),
        (PermissionError("nope"), "PermissionError: nope"),
    ],
)
def test_inspect_exception_on_first_call(monkeypatch, exc, expected):
    monkeypatch.setattr(inspect_mod, "_run", _scripted({BARE: exc}))
    s = inspect_repo("/r", timeout=2.0)
    assert s.error == expected
    assert s.path == Path("/r")
    assert s.branch is None
    assert s.remote_count == 0


def test_inspect_timeout_midway_keeps_earlier_fields(monkeypatch):
    responses = {
        BARE: (0, "false\n", ""),
        REMOTE: (0, "origin\nupstream\n", ""),
        HEAD: subprocess.TimeoutExpired(["git"], 1),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    s = inspect_repo("/r", timeout=1.5)
    assert s.error == "timeout after 1.5s"
    assert s.bare is False
    assert s.remote_count == 2
    assert s.branch is None


@pytest.mark.parametrize(
    ("out", "err", "expected"),
    [
        ("", "fatal: not a git repository\n", "fatal: not a git repository"),
        ("stdout msg\n", "  \n", "stdout msg"),
        ("", "", "git rev-parse failed"),
    ],
)
def test_inspect_rev_parse_failure_message(monkeypatch, out, err, expected):
    monkeypatch.setattr(inspect_mod, "_run", _scripted({BARE: (128, out, err)}))
    s = inspect_repo("/r")
    assert s.error == expected


def test_inspect_unparseable_tracking_counts_raise(monkeypatch):
    """Pins REFACTOR_NOTES B6: non-integer rev-list output escapes inspect_repo."""
    responses = {
        BARE: (0, "false\n", ""),
        HEAD: (0, "main\n", ""),
        UPSTREAM: (0, "origin/main\n", ""),
        TRACKING: (0, "x y\n", ""),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    with pytest.raises(ValueError):
        inspect_repo("/r")


def test_inspect_tracking_wrong_token_count_leaves_zero(monkeypatch):
    responses = {
        BARE: (0, "false\n", ""),
        HEAD: (0, "main\n", ""),
        UPSTREAM: (0, "origin/main\n", ""),
        TRACKING: (0, "3\n", ""),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    s = inspect_repo("/r")
    assert s.error is None
    assert s.has_upstream is True
    assert (s.ahead, s.behind) == (0, 0)


def test_inspect_later_command_failures_leave_defaults(monkeypatch):
    fail = (1, "ignored\n", "err")
    responses = {
        BARE: (0, "false\n", ""),
        REMOTE: fail,
        HEAD: fail,
        ("status", "--porcelain"): fail,
        ("stash", "list"): fail,
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    s = inspect_repo("/r")
    assert s.error is None
    assert s.remote_count == 0
    assert s.branch is None
    assert s.detached is False
    assert s.dirty is False
    assert s.stash_count == 0
    assert s.has_upstream is False


def test_inspect_tracking_rev_list_failure_leaves_zero(monkeypatch):
    responses = {
        BARE: (0, "false\n", ""),
        HEAD: (0, "main\n", ""),
        UPSTREAM: (0, "origin/main\n", ""),
        TRACKING: (128, "5 5\n", "bad"),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    s = inspect_repo("/r")
    assert s.has_upstream is True
    assert (s.ahead, s.behind) == (0, 0)


def test_inspect_detached_short_sha_failure(monkeypatch):
    responses = {
        BARE: (0, "false\n", ""),
        HEAD: (0, "HEAD\n", ""),
        ("rev-parse", "--short", "HEAD"): (1, "", ""),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    s = inspect_repo("/r")
    assert s.detached is True
    assert s.branch is None


# --- upstream_status -------------------------------------------------------


def test_upstream_timeout_after_master_keeps_master_pair(monkeypatch):
    responses = {
        ORIGIN_HEAD: (0, "origin/main\n", ""),
        MASTER_AB: (0, "1\t2\n", ""),
        SAME_VERIFY: subprocess.TimeoutExpired(["git"], 1),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    assert upstream_status("/r", branch="main") == (2, 1, None, None)


@pytest.mark.parametrize(
    "exc",
    [subprocess.TimeoutExpired(["git"], 1), OSError("x"), FileNotFoundError("git")],
)
def test_upstream_exceptions_are_swallowed(monkeypatch, exc):
    monkeypatch.setattr(inspect_mod, "_run", _scripted({ORIGIN_HEAD: exc}))
    assert upstream_status("/r", branch="main") == (None, None, None, None)


@pytest.mark.parametrize(
    "rev_list",
    [(0, "x y\n", ""), (0, "3\n", ""), (0, "", ""), (128, "1 2\n", "bad")],
)
def test_upstream_unparseable_counts_are_none(monkeypatch, rev_list):
    responses = {
        ORIGIN_HEAD: (0, "origin/main\n", ""),
        MASTER_AB: rev_list,
        SAME_VERIFY: (0, "", ""),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    assert upstream_status("/r", branch="main") == (None, None, None, None)


@pytest.mark.parametrize("origin_head", [(0, "origin/HEAD\n", ""), (0, "\n", "")])
def test_upstream_unresolved_origin_head_skips_master(monkeypatch, origin_head):
    responses = {
        ORIGIN_HEAD: origin_head,
        SAME_VERIFY: (0, "", ""),
        SAME_AB: (0, "0 4\n", ""),
    }
    monkeypatch.setattr(inspect_mod, "_run", _scripted(responses))
    assert upstream_status("/r", branch="main") == (None, None, 4, 0)


def test_upstream_no_branch_skips_same_name(monkeypatch):
    calls = []

    def _run(_path, args, _timeout):
        calls.append(tuple(args))
        return (1, "", "")

    monkeypatch.setattr(inspect_mod, "_run", _run)
    assert upstream_status("/r", branch=None) == (None, None, None, None)
    assert calls == [ORIGIN_HEAD]
