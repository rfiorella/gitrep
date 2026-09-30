# Test change proposals — gitrep

Status: **all entries (T1–T5, P1–P7) were approved and applied** on `refactor-cleanup`, each in its own `test:` commit.

## New characterization tests (T): proposed before the high-risk refactor steps

These pin **current** behavior, including behavior that REFACTOR_NOTES lists as a bug. They would go in new
files so the existing test files stay untouched. Each set lands in its own `test:` commit.

### T1: `tests/test_fetch_errors.py` (guards plan step 8)
Monkeypatch `gitrep.fetch.subprocess.run` to raise the following, then assert the exact `FetchResult`:
- `subprocess.TimeoutExpired(cmd, 3.0)` → `ok=False`, `stderr == "timeout after 3.0s"`.
- `FileNotFoundError("git")` → `ok=False`, `stderr.startswith("git not found: ")`.
- `PermissionError("x")` → `stderr == "PermissionError: x"`. `UnicodeDecodeError` → `stderr` starts with
  `"UnicodeDecodeError: "`.
- In every case `duration_s >= 0`.
- A non-zero return code yields `ok=False` with `stderr` stripped.

### T2: `tests/test_inspect_errors.py` (guards plan steps 4, 5, 8)
- `inspect_repo` when `_run` raises `TimeoutExpired` (at the first call, and at a later call) → `error ==
  "timeout after {t}s"`. Fields filled in before the failure keep their values.
- `FileNotFoundError` → `error` starts with `"git not found: "`. `OSError` → `"OSError: ..."`.
- `upstream_status` when `_run` raises `TimeoutExpired` on the 2nd call → the master pair is still filled in
  and the same-name pair is `(None, None)`.
- `upstream_status` when `rev-list` prints garbage or one token → `(None, None)` for that pair.
- **Pins B6:** `inspect_repo` with a stubbed `rev-list @{u}...HEAD` printing `"x y"` → raises `ValueError`.
  Only if you want the current behavior pinned; otherwise skip this case.

### T3: `tests/test_cli_extra.py` (guards plan step 7)
- `_confirm` with a monkeypatched `input`: `"y"`, `" YES "` → True; `""`, `"n"`, `"yep"` → False; `EOFError`
  → False.
- `--show-diff` with faked statuses (one dirty, one clean) → exactly one
  `["git", "-C", <dirty>, "status", "-s"]` call, and none for the clean repo.
- `--pull-clean` with no eligible repos → `"no clean+behind repos to pull"`, and `_confirm` is not called.
- Eligibility: each of `dirty`, `detached`, `not has_upstream`, `error`, `behind == 0` alone excludes a repo.
- Missing root → stdout contains `root not found`, exit code 2.

### T4: `tests/test_report_notes.py` (guards plan step 6)
- The note column shows `error: boom` when `error` is set, `no upstream`, `detached`, `bare`, or empty,
  including the precedence (error > no-upstream > detached > bare).
- `_relpath` / `render_table(root=...)` shows the repo relative to root; a path outside root is printed in
  full.
- Branch `None` renders as `-`.

### T5 (optional): golden output snapshot
- A table rendered with `Console(width=200, force_terminal=False)` for a fixed list of 4 fake statuses, with
  and without `show_upstream`/`show_remote`, compared to an inline expected string. This catches any
  accidental change to columns, justification, or markup during steps 6–7.

## Changes to existing tests (P): optional cleanups, low priority

None of these block the refactor.

| id | test / file | change | why |
|---|---|---|---|
| P1 | `tests/__pycache__/*.pyc` (6 files) | `git rm --cached tests/__pycache__` | Build artifacts are tracked despite `.gitignore`. They go stale and differ per Python version. Test source is unchanged. |
| P2 | `conftest.py:53-62` `git_env_extra` | Delete it. `_git` duplicates the same dict (`14-23`), so share one module constant | The fixture is unused (verified by grep) and duplicates the dict. |
| P3 | `test_fetch.py:43-49` `test_fetch_no_remote` | Assert `fr.ok is True` instead of `isinstance(fr.ok, bool)` | As written the test can't fail. It passes on git 2.56. |
| P4 | `test_inspect.py:350-351` | Rewrite the comment `"No same-name branch ... wait, there IS one."` | A confusing leftover. The assertion is fine. |
| P5 | `test_discovery.py:30` | Fix the comment: it says a "`.git`-named subdir-look-alike" is created, but the test creates `subdir/` | The comment does not match the code. |
| P6 | `test_fetch.py:6-15`, `test_inspect.py:56-66`, `test_inspect.py:148-171` | Merge the three clone-with-upstream helpers into one conftest fixture | Near-duplicates. |
| P7 | `test_cli.py` (6 copies), `test_report.py` (9 copies) | Share a `fake_status(**kw)` helper, a `spy_run` fixture, and a `render(table) -> str` helper | Heavy copy-paste boilerplate. |
