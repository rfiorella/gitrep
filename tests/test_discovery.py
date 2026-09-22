from __future__ import annotations

from gitrep.discovery import discover_repos


def test_discovers_top_and_nested(repo_tree):
    repos = discover_repos(repo_tree)
    names = {p.name for p in repos}
    assert "a" in names
    assert "b" in names
    assert "c" in names
    assert "with_sub" in names


def test_skips_submodule_gitfile_by_default(repo_tree):
    repos = discover_repos(repo_tree)
    assert not any(p.name == "submod" for p in repos)


def test_includes_submodule_when_requested(repo_tree):
    repos = discover_repos(repo_tree, skip_submodules=False)
    assert any(p.name == "submod" for p in repos)


def test_does_not_descend_into_repo_worktree(tmp_path, make_repo, commit):
    root = tmp_path / "root"
    root.mkdir()
    outer = make_repo("root/outer")
    commit(outer, "f.txt")
    # create a `.git`-named subdir-look-alike inside outer's worktree; should NOT be re-walked
    (outer / "subdir").mkdir()
    (outer / "subdir" / "x.txt").write_text("x")
    repos = discover_repos(root)
    assert len(repos) == 1
    assert repos[0].name == "outer"


def test_missing_root(tmp_path):
    assert discover_repos(tmp_path / "does_not_exist") == []


def test_empty_root(tmp_path):
    assert discover_repos(tmp_path) == []


def test_returns_sorted(tmp_path, make_repo, commit):
    for n in ["zeta", "alpha", "mu"]:
        r = make_repo(n)
        commit(r, "f.txt")
    repos = discover_repos(tmp_path)
    paths = [str(p) for p in repos]
    assert paths == sorted(paths)
