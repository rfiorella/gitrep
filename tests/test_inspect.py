from __future__ import annotations

from gitrep.inspect import inspect_repo, upstream_status


def test_clean_repo(make_repo, commit):
    r = make_repo("clean")
    commit(r, "f.txt")
    s = inspect_repo(r)
    assert s.error is None
    assert s.branch == "main"
    assert s.detached is False
    assert s.dirty is False
    assert s.ahead == 0 and s.behind == 0
    assert s.has_upstream is False
    assert s.stash_count == 0
    assert s.bare is False


def test_dirty_unstaged(make_repo, commit):
    r = make_repo("dirty")
    commit(r, "f.txt")
    (r / "f.txt").write_text("changed")
    s = inspect_repo(r)
    assert s.dirty is True


def test_dirty_staged(make_repo, commit, git):
    r = make_repo("staged")
    commit(r, "f.txt")
    (r / "g.txt").write_text("new")
    git(r, "add", "g.txt")
    s = inspect_repo(r)
    assert s.dirty is True


def test_detached_head(make_repo, commit, git):
    r = make_repo("detached")
    commit(r, "a.txt")
    commit(r, "b.txt")
    proc = git(r, "rev-parse", "HEAD~1")
    sha = proc.stdout.strip()
    git(r, "checkout", "--detach", sha)
    s = inspect_repo(r)
    assert s.detached is True
    assert s.has_upstream is False


def test_no_upstream(make_repo, commit):
    r = make_repo("noup")
    commit(r, "f.txt")
    s = inspect_repo(r)
    assert s.has_upstream is False


def _setup_upstream(make_repo, commit, git, name: str):
    upstream = make_repo(f"{name}-up")
    commit(upstream, "f.txt")
    commit(upstream, "g.txt")
    work = make_repo(name)
    # configure work as a clone of upstream
    git(work, "remote", "add", "origin", str(upstream))
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", "main", "origin/main")
    git(work, "branch", "--set-upstream-to=origin/main", "main")
    return upstream, work


def test_ahead_behind_clean(make_repo, commit, git):
    _upstream, work = _setup_upstream(make_repo, commit, git, "ab1")
    s = inspect_repo(work)
    assert s.has_upstream is True
    assert s.ahead == 0 and s.behind == 0


def test_ahead_only(make_repo, commit, git):
    _upstream, work = _setup_upstream(make_repo, commit, git, "ahead")
    commit(work, "h.txt")
    commit(work, "i.txt")
    s = inspect_repo(work)
    assert s.ahead == 2
    assert s.behind == 0


def test_behind_only(make_repo, commit, git):
    upstream, work = _setup_upstream(make_repo, commit, git, "behind")
    commit(upstream, "h.txt")
    commit(upstream, "i.txt")
    commit(upstream, "j.txt")
    git(work, "fetch", "-q", "origin")
    s = inspect_repo(work)
    assert s.ahead == 0
    assert s.behind == 3


def test_ahead_and_behind(make_repo, commit, git):
    upstream, work = _setup_upstream(make_repo, commit, git, "both")
    commit(upstream, "u.txt")
    commit(work, "w.txt")
    git(work, "fetch", "-q", "origin")
    s = inspect_repo(work)
    assert s.ahead == 1
    assert s.behind == 1


def test_stash_count(make_repo, commit, git):
    r = make_repo("stashy")
    commit(r, "f.txt")
    (r / "f.txt").write_text("a")
    git(r, "stash", "push", "-q", "-m", "first")
    (r / "f.txt").write_text("b")
    git(r, "stash", "push", "-q", "-m", "second")
    s = inspect_repo(r)
    assert s.stash_count == 2


def test_bare_repo(tmp_path, git):
    bare = tmp_path / "bare.git"
    bare.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q", "--bare"], cwd=str(bare), check=True)
    s = inspect_repo(bare)
    assert s.bare is True
    assert s.dirty is False


def test_corrupt_repo_records_error(tmp_path):
    fake = tmp_path / "fake"
    (fake / ".git").mkdir(parents=True)
    s = inspect_repo(fake)
    assert s.error is not None


def test_needs_attention_property(make_repo, commit):
    r = make_repo("clean2")
    commit(r, "f.txt")
    s = inspect_repo(r)
    assert s.needs_attention is False
    (r / "f.txt").write_text("y")
    s2 = inspect_repo(r)
    assert s2.needs_attention is True


# --- upstream-status helpers ----------------------------------------------


def _setup_upstream_with_head(
    make_repo, commit, git, name: str, *, branch: str = "main"
):
    """Set up an upstream + work clone with origin/HEAD pointing at <branch>.

    Returns ``(upstream, work)`` where ``work`` is checked out on ``branch``
    tracking ``origin/<branch>``.
    """
    upstream = make_repo(f"{name}-up", initial_branch=branch)
    commit(upstream, "f.txt")
    commit(upstream, "g.txt")
    work = make_repo(name, initial_branch=branch)
    git(work, "remote", "add", "origin", str(upstream))
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", branch, f"origin/{branch}")
    git(work, "branch", f"--set-upstream-to=origin/{branch}", branch)
    # Set origin/HEAD explicitly so upstream_status can resolve it.
    git(
        work,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        f"refs/remotes/origin/{branch}",
    )
    return upstream, work


# --- upstream_master tests ------------------------------------------------


def test_upstream_master_clean(make_repo, commit, git):
    _upstream, work = _setup_upstream_with_head(make_repo, commit, git, "umc")
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_master_ahead == 0
    assert s.upstream_master_behind == 0


def test_upstream_master_ahead(make_repo, commit, git):
    _upstream, work = _setup_upstream_with_head(make_repo, commit, git, "uma")
    commit(work, "h.txt")
    commit(work, "i.txt")
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_master_ahead == 2
    assert s.upstream_master_behind == 0


def test_upstream_master_behind(make_repo, commit, git):
    upstream, work = _setup_upstream_with_head(make_repo, commit, git, "umb")
    commit(upstream, "h.txt")
    commit(upstream, "i.txt")
    commit(upstream, "j.txt")
    git(work, "fetch", "-q", "origin")
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_master_ahead == 0
    assert s.upstream_master_behind == 3


def test_upstream_master_ahead_and_behind_matches_rev_list(make_repo, commit, git):
    upstream, work = _setup_upstream_with_head(make_repo, commit, git, "umab")
    commit(upstream, "u.txt")
    commit(work, "w.txt")
    git(work, "fetch", "-q", "origin")
    s = inspect_repo(work, with_upstream=True)
    raw = git(work, "rev-list", "--left-right", "--count", "origin/main...HEAD")
    behind_str, ahead_str = raw.stdout.split()
    assert s.upstream_master_ahead == int(ahead_str)
    assert s.upstream_master_behind == int(behind_str)


def test_upstream_master_blank_when_origin_head_unset(make_repo, commit, git, tmp_path):
    """If origin/HEAD is not configured, the master pair is None/None."""
    upstream = make_repo("umblank-up")
    commit(upstream, "f.txt")
    work = make_repo("umblank")
    git(work, "remote", "add", "origin", str(upstream))
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", "main", "origin/main")
    git(work, "branch", "--set-upstream-to=origin/main", "main")
    # Modern git may auto-create origin/HEAD on fetch from a single-branch
    # remote; explicitly delete it to simulate the "unset" scenario.
    head_ref = work / ".git" / "refs" / "remotes" / "origin" / "HEAD"
    if head_ref.exists():
        head_ref.unlink()
    # Also ensure there's no packed-refs entry for it.
    packed = work / ".git" / "packed-refs"
    if packed.exists():
        lines = [
            ln
            for ln in packed.read_text().splitlines()
            if "refs/remotes/origin/HEAD" not in ln
        ]
        packed.write_text("\n".join(lines) + ("\n" if lines else ""))
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_master_ahead is None
    assert s.upstream_master_behind is None


# --- upstream_same_name tests ---------------------------------------------


def test_upstream_same_name_clean(make_repo, commit, git):
    upstream, work = _setup_upstream_with_head(make_repo, commit, git, "usnc")
    # Create a feature branch on upstream first, then check it out in work.
    git(upstream, "checkout", "-q", "-b", "feature")
    commit(upstream, "feat.txt")
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", "feature", "origin/feature")
    git(work, "branch", "--set-upstream-to=origin/feature", "feature")
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_same_name_ahead == 0
    assert s.upstream_same_name_behind == 0


def test_upstream_same_name_ahead(make_repo, commit, git):
    upstream, work = _setup_upstream_with_head(make_repo, commit, git, "usna")
    git(upstream, "checkout", "-q", "-b", "feature")
    commit(upstream, "feat.txt")
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", "feature", "origin/feature")
    commit(work, "local1.txt")
    commit(work, "local2.txt")
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_same_name_ahead == 2
    assert s.upstream_same_name_behind == 0


def test_upstream_same_name_matches_rev_list(make_repo, commit, git):
    upstream, work = _setup_upstream_with_head(make_repo, commit, git, "usnab")
    git(upstream, "checkout", "-q", "-b", "feature")
    commit(upstream, "feat.txt")
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-B", "feature", "origin/feature")
    # both diverge
    commit(upstream, "u2.txt")
    commit(work, "w1.txt")
    git(work, "fetch", "-q", "origin")
    s = inspect_repo(work, with_upstream=True)
    raw = git(work, "rev-list", "--left-right", "--count", "origin/feature...HEAD")
    behind_str, ahead_str = raw.stdout.split()
    assert s.upstream_same_name_ahead == int(ahead_str)
    assert s.upstream_same_name_behind == int(behind_str)


# --- upstream_missing tests -----------------------------------------------


def test_upstream_missing_same_name(make_repo, commit, git):
    """Local feature branch with no matching branch on origin -> None pair."""
    _upstream, work = _setup_upstream_with_head(make_repo, commit, git, "usnm")
    # Create the feature branch only locally.
    git(work, "checkout", "-q", "-b", "feature-local-only")
    commit(work, "local.txt")
    s = inspect_repo(work, with_upstream=True)
    assert s.upstream_same_name_ahead is None
    assert s.upstream_same_name_behind is None
    # Master pair should still be populated since origin/HEAD is set.
    assert s.upstream_master_ahead is not None
    assert s.upstream_master_behind is not None


def test_upstream_missing_no_origin(make_repo, commit):
    """No origin remote at all -> all four upstream fields None."""
    r = make_repo("noorigin")
    commit(r, "f.txt")
    s = inspect_repo(r, with_upstream=True)
    assert s.upstream_master_ahead is None
    assert s.upstream_master_behind is None
    assert s.upstream_same_name_ahead is None
    assert s.upstream_same_name_behind is None


def test_upstream_missing_detached_head(make_repo, commit, git):
    """Detached HEAD -> all four upstream fields None (no current branch)."""
    _upstream, work = _setup_upstream_with_head(make_repo, commit, git, "usnd")
    commit(work, "extra.txt")
    proc = git(work, "rev-parse", "HEAD~1")
    sha = proc.stdout.strip()
    git(work, "checkout", "--detach", sha)
    s = inspect_repo(work, with_upstream=True)
    assert s.detached is True
    # In detached state we still try the master pair (it can resolve), but
    # same-name must be None because there is no real branch name.
    assert s.upstream_same_name_ahead is None
    assert s.upstream_same_name_behind is None


def test_upstream_status_default_off(make_repo, commit, git):
    """Without with_upstream=True, the four fields stay None."""
    _upstream, work = _setup_upstream_with_head(make_repo, commit, git, "off")
    s = inspect_repo(work)  # default with_upstream=False
    assert s.upstream_master_ahead is None
    assert s.upstream_master_behind is None
    assert s.upstream_same_name_ahead is None
    assert s.upstream_same_name_behind is None


def test_upstream_status_helper_direct(make_repo, commit, git):
    """upstream_status() returns the same four ints as inspect_repo populates."""
    _upstream, work = _setup_upstream_with_head(make_repo, commit, git, "helper")
    commit(work, "h.txt")
    ma, mb, sa, sb = upstream_status(work, branch="main")
    assert ma == 1
    assert mb == 0
    # No same-name branch on origin called "main"... wait, there IS one.
    # origin/main exists, so same-name resolves equal to master in this case.
    assert sa == 1
    assert sb == 0


# --- remote_count tests ----------------------------------------------------

def test_remote_count_zero_remotes(make_repo, commit):
    r = make_repo("noremotes")
    commit(r, "f.txt")
    s = inspect_repo(r)
    assert s.remote_count == 0


def test_remote_count_one_remote(make_repo, commit, git):
    upstream = make_repo("onerc-up")
    commit(upstream, "f.txt")
    work = make_repo("onerc")
    commit(work, "f.txt")
    git(work, "remote", "add", "origin", str(upstream))
    s = inspect_repo(work)
    assert s.remote_count == 1


def test_remote_count_two_remotes(make_repo, commit, git):
    origin = make_repo("tworc-origin")
    commit(origin, "f.txt")
    other = make_repo("tworc-upstream")
    commit(other, "f.txt")
    work = make_repo("tworc")
    commit(work, "f.txt")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "remote", "add", "upstream", str(other))
    s = inspect_repo(work)
    assert s.remote_count == 2
