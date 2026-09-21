from __future__ import annotations

import json
import subprocess
import sys

import pytest

from gitrep import cli as cli_mod


def test_cli_no_fetch_default(repo_tree, capsys):
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch"])
    assert rc == 0


def test_cli_json_no_fetch(repo_tree, capsys):
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--json", "--all"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) >= 4
    for entry in parsed:
        for key in ("path", "branch", "dirty", "ahead", "behind", "has_upstream", "stash_count"):
            assert key in entry


def test_cli_all_no_fetch(repo_tree):
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--all"])
    assert rc == 0


def test_cli_missing_root(tmp_path):
    rc = cli_mod.main(["--root", str(tmp_path / "nope"), "--no-fetch"])
    assert rc == 2


def test_cli_no_repos(tmp_path, capsys):
    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch"])
    assert rc == 0


def test_cli_default_root_is_code():
    # parser default sanity check; don't actually scan /code
    parser = cli_mod._build_parser()
    ns = parser.parse_args([])
    assert ns.root == "/code"
    assert ns.all is False
    assert ns.json is False
    assert ns.no_fetch is False
    assert ns.workers == 16


def test_cli_default_invokes_fetch_once(repo_tree, monkeypatch):
    calls = {"n": 0, "repos": None}

    def fake_fetch_all(repos, *, max_workers=16, timeout=30.0):
        calls["n"] += 1
        calls["repos"] = list(repos)
        return {p: object() for p in repos}

    monkeypatch.setattr(cli_mod, "fetch_all", fake_fetch_all)
    rc = cli_mod.main(["--root", str(repo_tree)])
    assert rc == 0
    assert calls["n"] == 1
    assert len(calls["repos"]) >= 4


def test_cli_no_fetch_does_not_invoke_fetch(repo_tree, monkeypatch):
    calls = {"n": 0}

    def fake_fetch_all(repos, *, max_workers=16, timeout=30.0):
        calls["n"] += 1
        return {}

    monkeypatch.setattr(cli_mod, "fetch_all", fake_fetch_all)
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch"])
    assert rc == 0
    assert calls["n"] == 0


def test_cli_no_pull_when_pull_clean_absent(repo_tree, monkeypatch):
    runs = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        runs.append(list(cmd))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(cli_mod.subprocess, "run", spy_run)
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {p: None for p in repos})
    rc = cli_mod.main(["--root", str(repo_tree)])
    assert rc == 0
    for cmd in runs:
        assert "pull" not in cmd, f"unexpected pull invocation: {cmd}"
        assert "commit" not in cmd, f"unexpected commit invocation: {cmd}"
        assert "push" not in cmd, f"unexpected push invocation: {cmd}"


def test_cli_pull_clean_aborts_without_confirmation(repo_tree, monkeypatch):
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {p: None for p in repos})
    # Force a "clean+behind" target by stubbing inspect_repo
    from gitrep.inspect import RepoStatus
    from pathlib import Path

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        return RepoStatus(
            path=Path(path), branch="main", detached=False, dirty=False,
            ahead=0, behind=2, has_upstream=True, stash_count=0, bare=False, error=None,
            remote_count=1,
        )

    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    monkeypatch.setattr(cli_mod, "_confirm", lambda prompt: False)

    runs = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        runs.append(list(cmd))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(cli_mod.subprocess, "run", spy_run)
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--pull-clean"])
    assert rc == 0
    for cmd in runs:
        assert "pull" not in cmd


def test_cli_upstream_status_flag_accepted():
    parser = cli_mod._build_parser()
    ns = parser.parse_args(["--upstream-status"])
    assert ns.upstream_status is True
    ns2 = parser.parse_args([])
    assert ns2.upstream_status is False


def test_cli_upstream_status_no_repos_exits_zero(tmp_path):
    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch", "--upstream-status"])
    assert rc == 0


def test_cli_upstream_status_json_includes_keys(repo_tree, capsys):
    rc = cli_mod.main([
        "--root", str(repo_tree), "--no-fetch", "--json", "--all", "--upstream-status",
    ])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert isinstance(parsed, list) and len(parsed) >= 1
    for entry in parsed:
        for key in (
            "upstream_master_ahead",
            "upstream_master_behind",
            "upstream_same_name_ahead",
            "upstream_same_name_behind",
        ):
            assert key in entry


def test_cli_json_without_upstream_status_omits_keys(repo_tree, capsys):
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--json", "--all"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert isinstance(parsed, list) and len(parsed) >= 1
    for entry in parsed:
        for key in (
            "upstream_master_ahead",
            "upstream_master_behind",
            "upstream_same_name_ahead",
            "upstream_same_name_behind",
        ):
            assert key not in entry


def test_cli_upstream_status_passes_with_upstream_to_inspect(repo_tree, monkeypatch):
    seen = {"with_upstream": None}
    from gitrep.inspect import RepoStatus
    from pathlib import Path

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        seen["with_upstream"] = with_upstream
        return RepoStatus(
            path=Path(path), branch="main", detached=False, dirty=False,
            ahead=0, behind=0, has_upstream=False, stash_count=0, bare=False, error=None,
            remote_count=1,
        )

    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--upstream-status"])
    assert rc == 0
    assert seen["with_upstream"] is True


def test_cli_pull_clean_runs_pull_after_confirmation(repo_tree, monkeypatch):
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {p: None for p in repos})
    from gitrep.inspect import RepoStatus
    from pathlib import Path

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        return RepoStatus(
            path=Path(path), branch="main", detached=False, dirty=False,
            ahead=0, behind=2, has_upstream=True, stash_count=0, bare=False, error=None,
            remote_count=1,
        )

    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    monkeypatch.setattr(cli_mod, "_confirm", lambda prompt: True)

    runs = []

    def spy_run(cmd, *a, **kw):
        runs.append(list(cmd))
        # don't actually run pulls; return a dummy
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(cli_mod.subprocess, "run", spy_run)
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--pull-clean"])
    assert rc == 0
    pulls = [c for c in runs if "pull" in c]
    assert len(pulls) >= 1
    for c in pulls:
        assert "--ff-only" in c


def test_pull_clean_multi_remote_excluded(repo_tree, monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {p: None for p in repos})
    from gitrep.inspect import RepoStatus
    from pathlib import Path

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        return RepoStatus(
            path=Path(path), branch="main", detached=False, dirty=False,
            ahead=0, behind=2, has_upstream=True, stash_count=0, bare=False, error=None,
            remote_count=2,
        )

    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    monkeypatch.setattr(cli_mod, "_confirm", lambda prompt: True)

    runs = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        runs.append(list(cmd))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(cli_mod.subprocess, "run", spy_run)
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--pull-clean"])
    assert rc == 0
    out = capsys.readouterr().out
    # every repo in the fixture has two remotes, so no target list is
    # ever printed and no path is offered for pull.
    assert "pull-clean targets" not in out
    assert "no clean+behind repos to pull" in out
    for cmd in runs:
        assert "pull" not in cmd, f"unexpected pull invocation: {cmd}"


def test_pull_clean_single_remote_included(repo_tree, monkeypatch):
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {p: None for p in repos})
    from gitrep.inspect import RepoStatus
    from pathlib import Path

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        return RepoStatus(
            path=Path(path), branch="main", detached=False, dirty=False,
            ahead=0, behind=2, has_upstream=True, stash_count=0, bare=False, error=None,
            remote_count=1,
        )

    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    monkeypatch.setattr(cli_mod, "_confirm", lambda prompt: True)

    runs = []

    def spy_run(cmd, *a, **kw):
        runs.append(list(cmd))
        # don't actually run pulls; return a dummy
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(cli_mod.subprocess, "run", spy_run)
    rc = cli_mod.main(["--root", str(repo_tree), "--no-fetch", "--pull-clean"])
    assert rc == 0
    pulls = [c for c in runs if "pull" in c]
    assert len(pulls) >= 1
    for c in pulls:
        assert "--ff-only" in c


def test_pull_clean_announces_multi_remote_skips(tmp_path, monkeypatch, capsys):
    from gitrep.inspect import RepoStatus
    from pathlib import Path

    single_path = tmp_path / "single_remote_repo"
    multi_path = tmp_path / "multi_remote_repo"

    def fake_discover(root, *, skip_submodules=True):
        return [single_path, multi_path]

    def fake_inspect(path, *, timeout=5.0, with_upstream=False):
        path = Path(path)
        is_multi = path == multi_path
        return RepoStatus(
            path=path, branch="main", detached=False, dirty=False,
            ahead=0, behind=2, has_upstream=True, stash_count=0, bare=False, error=None,
            remote_count=2 if is_multi else 1,
        )

    captured = {"before_confirm": None}

    def fake_confirm(prompt):
        # Snapshot everything printed so far, *before* answering the
        # prompt, so we can prove the skip block was already on screen
        # when the confirmation was requested.
        captured["before_confirm"] = capsys.readouterr().out
        return False

    monkeypatch.setattr(cli_mod, "discover_repos", fake_discover)
    monkeypatch.setattr(cli_mod, "fetch_all", lambda repos, **kw: {p: None for p in repos})
    monkeypatch.setattr(cli_mod, "inspect_repo", fake_inspect)
    monkeypatch.setattr(cli_mod, "_confirm", fake_confirm)

    runs = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        runs.append(list(cmd))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(cli_mod.subprocess, "run", spy_run)

    # Fixture paths under tmp_path can be long; give the console enough
    # width that rich doesn't soft-wrap a path across two lines, which
    # would otherwise break the line-based block search below.
    monkeypatch.setenv("COLUMNS", "400")

    rc = cli_mod.main(["--root", str(tmp_path), "--no-fetch", "--pull-clean"])
    assert rc == 0
    for cmd in runs:
        assert "pull" not in cmd, f"unexpected pull invocation: {cmd}"

    out = captured["before_confirm"]
    assert out is not None, "_confirm was never called"

    lines = out.splitlines()
    target_idx = next(
        (i for i, ln in enumerate(lines) if "pull-clean targets" in ln), None
    )
    skip_idx = next(
        (i for i, ln in enumerate(lines) if "multiple remotes" in ln), None
    )
    assert target_idx is not None, "target block header not found before prompt"
    assert skip_idx is not None, "skip block header not found before prompt"
    assert target_idx < skip_idx, "skip block must be printed after the target block"

    target_block = "\n".join(lines[target_idx:skip_idx])
    skip_block = "\n".join(lines[skip_idx:])

    assert str(single_path) in target_block
    assert str(multi_path) not in target_block
    assert str(multi_path) in skip_block
    assert str(single_path) not in skip_block
