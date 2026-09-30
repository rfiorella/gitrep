"""Characterization tests for untested CLI paths (TEST_CHANGE_PROPOSALS T3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gitrep import cli as cli_mod
from gitrep.inspect import RepoStatus


def _status(path, **kw) -> RepoStatus:
    base = {
        "path": Path(path),
        "branch": "main",
        "detached": False,
        "dirty": False,
        "ahead": 0,
        "behind": 2,
        "has_upstream": True,
        "stash_count": 0,
        "bare": False,
        "error": None,
        "remote_count": 1,
    }
    base.update(kw)
    return RepoStatus(**base)


class _Done:
    returncode = 0


@pytest.fixture
def spy_run(monkeypatch):
    runs: list[list[str]] = []

    def _run(cmd, *_a, **_kw):
        runs.append(list(cmd))
        return _Done()

    monkeypatch.setattr(cli_mod.subprocess, "run", _run)
    return runs


@pytest.fixture
def fake_pipeline(monkeypatch, tmp_path):
    """Stub discovery/fetch/inspect; returns a dict to fill with statuses by path."""
    statuses: dict[Path, RepoStatus] = {}
    monkeypatch.setattr(
        cli_mod, "discover_repos", lambda root, *, skip_submodules=True: list(statuses)
    )
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {})
    monkeypatch.setattr(
        cli_mod,
        "inspect_repo",
        lambda path, *, timeout=5.0, with_upstream=False: statuses[Path(path)],
    )
    monkeypatch.setenv("COLUMNS", "400")
    return statuses


# --- _confirm --------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("y", True),
        (" YES ", True),
        ("Yes", True),
        ("", False),
        ("n", False),
        ("yep", False),
    ],
)
def test_confirm_answers(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    assert cli_mod._confirm("? ") is expected


def test_confirm_eof_is_no(monkeypatch):
    def _eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert cli_mod._confirm("? ") is False


# --- argument plumbing -----------------------------------------------------


def test_main_passes_options_through(monkeypatch, tmp_path):
    seen = {}

    def fake_discover(root, *, skip_submodules=True):
        seen["discover"] = (root, skip_submodules)
        return [tmp_path / "r"]

    def fake_fetch(repos, *, max_workers=16, timeout=30.0):
        seen["fetch"] = (list(repos), max_workers, timeout)
        return {}

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        seen["inspect"] = (path, timeout, with_upstream)
        return _status(path, behind=0)

    monkeypatch.setattr(cli_mod, "discover_repos", fake_discover)
    monkeypatch.setattr(cli_mod, "fetch_all", fake_fetch)
    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    argv = ["--root", str(tmp_path), "--workers", "3", "--fetch-timeout", "4.5"]
    argv += ["--inspect-timeout", "2.5", "--include-submodules", "--upstream-status"]
    assert cli_mod.main(argv) == 0
    assert seen["discover"] == (tmp_path, False)
    assert seen["fetch"] == ([tmp_path / "r"], 3, 4.5)
    assert seen["inspect"] == (tmp_path / "r", 2.5, True)


def test_missing_root_message_and_exit_code(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "400")
    missing = tmp_path / "nope"
    assert cli_mod.main(["--root", str(missing), "--no-fetch"]) == 2
    assert f"root not found: {missing}" in capsys.readouterr().out


def test_no_repos_message(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "400")
    assert cli_mod.main(["--root", str(tmp_path), "--no-fetch"]) == 0
    assert f"no repos found under {tmp_path}" in capsys.readouterr().out


# --- --show-diff -----------------------------------------------------------


def test_show_diff_runs_status_for_dirty_only(fake_pipeline, spy_run, tmp_path):
    dirty, clean = tmp_path / "dirty", tmp_path / "clean"
    fake_pipeline[dirty] = _status(dirty, dirty=True)
    fake_pipeline[clean] = _status(clean)
    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch", "--show-diff"])
    assert rc == 0
    assert spy_run == [["git", "-C", str(dirty), "status", "-s"]]


# --- --pull-clean eligibility ----------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"dirty": True},
        {"detached": True},
        {"has_upstream": False},
        {"error": "boom"},
        {"behind": 0},
    ],
)
def test_pull_clean_ineligible(
    fake_pipeline, spy_run, tmp_path, monkeypatch, capsys, override
):
    p = tmp_path / "r"
    fake_pipeline[p] = _status(p, **override)
    confirmed = []
    monkeypatch.setattr(cli_mod, "_confirm", lambda prompt: confirmed.append(prompt))
    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch", "--pull-clean"])
    assert rc == 0
    assert "no clean+behind repos to pull" in capsys.readouterr().out
    assert confirmed == []
    assert spy_run == []


def test_pull_clean_pulls_targets_in_order(
    fake_pipeline, spy_run, tmp_path, monkeypatch
):
    a, b = tmp_path / "a", tmp_path / "b"
    fake_pipeline[a] = _status(a)
    fake_pipeline[b] = _status(b)
    prompts = []
    monkeypatch.setattr(
        cli_mod, "_confirm", lambda prompt: prompts.append(prompt) or True
    )
    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch", "--pull-clean"])
    assert rc == 0
    assert prompts == ["proceed with pull on these repos? [y/N] "]
    assert spy_run == [
        ["git", "-C", str(a), "pull", "--ff-only"],
        ["git", "-C", str(b), "pull", "--ff-only"],
    ]


def test_pull_clean_declined_prints_aborted(
    fake_pipeline, spy_run, tmp_path, monkeypatch, capsys
):
    p = tmp_path / "r"
    fake_pipeline[p] = _status(p)
    monkeypatch.setattr(cli_mod, "_confirm", lambda prompt: False)
    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch", "--pull-clean"])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"{p} (behind 2)" in out
    assert "aborted" in out
    assert spy_run == []
