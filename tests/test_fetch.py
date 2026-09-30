from __future__ import annotations

from gitrep.fetch import fetch_all


def test_fetch_all_empty():
    assert fetch_all([]) == {}


def test_fetch_all_success(clone_pair):
    pairs = [clone_pair(f"r{i}") for i in range(3)]
    repos = [w for _, w in pairs]
    res = fetch_all(repos, max_workers=4, timeout=10.0)
    assert set(res.keys()) == set(repos)
    for p, fr in res.items():
        assert fr.ok is True, f"{p}: {fr.stderr}"
        assert fr.duration_s >= 0


def test_fetch_one_bogus_does_not_abort(clone_pair, make_repo, commit, git, tmp_path):
    _upstream, work = clone_pair("good")
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
    # `git fetch --all` with no remotes is a successful no-op
    assert fr.ok is True
