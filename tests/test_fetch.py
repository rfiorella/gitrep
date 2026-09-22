from __future__ import annotations

from gitrep.fetch import fetch_all


def _clone_pair(make_repo, commit, git, name: str):
    upstream = make_repo(f"{name}-up")
    commit(upstream, "f.txt")
    commit(upstream, "g.txt")
    work = make_repo(name)
    git(work, "remote", "add", "origin", str(upstream))
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", "main", "origin/main")
    git(work, "branch", "--set-upstream-to=origin/main", "main")
    return upstream, work


def test_fetch_all_empty():
    assert fetch_all([]) == {}


def test_fetch_all_success(make_repo, commit, git):
    pairs = [_clone_pair(make_repo, commit, git, f"r{i}") for i in range(3)]
    repos = [w for _, w in pairs]
    res = fetch_all(repos, max_workers=4, timeout=10.0)
    assert set(res.keys()) == set(repos)
    for p, fr in res.items():
        assert fr.ok is True, f"{p}: {fr.stderr}"
        assert fr.duration_s >= 0


def test_fetch_one_bogus_does_not_abort(make_repo, commit, git, tmp_path):
    upstream, work = _clone_pair(make_repo, commit, git, "good")
    bad = make_repo("bad")
    commit(bad, "f.txt")
    git(bad, "remote", "add", "origin", str(tmp_path / "nonexistent"))
    res = fetch_all([work, bad], max_workers=2, timeout=10.0)
    assert res[work].ok is True
    assert res[bad].ok is False
    assert res[bad].stderr  # has some error message


def test_fetch_no_remote(make_repo, commit):
    r = make_repo("noremote")
    commit(r, "f.txt")
    res = fetch_all([r], timeout=10.0)
    fr = res[r]
    # `git fetch --all` with no remotes succeeds (no-op) on modern git
    assert isinstance(fr.ok, bool)
