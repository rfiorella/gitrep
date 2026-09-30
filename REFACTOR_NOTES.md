# Refactor notes — gitrep

Baseline commit: `9e0809b`. Branch: `refactor-cleanup`. Phase 2 is complete.

## Bugs found (not fixed; behavior left as-is)

B1–B3 were reproduced against throwaway repos on 2026-09-29. B4 and B6 come from reading the code.

### B1: `--include-submodules` never finds real submodules (reproduced)
- **Where:** `discovery.py:32-35`. When a dir has a `.git` *directory*, it is appended and `dirnames[:] = []`
  prunes the walk. A real submodule lives inside its parent's worktree, so the walk never reaches it.
- **Symptom:** a parent repo containing `git submodule add ../lib sub` gives
  `discover_repos(root, skip_submodules=False)` → `['lib', 'parent', ...]`, with no `parent/sub`. The flag
  only finds `.git`-file dirs that are *not* inside another repo (for example `git worktree add` targets).
  The test fixture (`conftest.py:97-102`) works around this on purpose.
- **Suggested fix:** when `skip_submodules=False`, keep descending into a repo's worktree but only collect
  `.git`-file dirs. Or re-document the flag as "include linked worktrees / gitfile repos".

### B2: fetch failures are silently discarded (reproduced)
- **Where:** `cli.py:107` ignores the return value of `fetch_all()`.
- **Symptom:** a repo whose `origin` points at a nonexistent path fetches with `ok=False`, but the table shows
  it as a normal repo (`badremote | main | ... | no upstream`), exit code 0. Without `--all`, a repo that
  can't fetch and is otherwise clean is not shown at all, and its ahead/behind numbers are silently stale.
- **Suggested fix:** pass fetch results into rendering and show `fetch failed: <stderr>` as a note (and treat
  it as needing attention).

### B3: `--json` output is not pure JSON when combined with other flags (reproduced)
- **Where:** `cli.py:97`, `102`, `139-140`, `148-169`. Everything goes through a rich `Console` on stdout.
- **Symptom:** `gitrep --json --pull-clean --no-fetch` prints `[]` followed by
  `no clean+behind repos to pull` on stdout, so `json.loads` fails. The same happens with `--show-diff`
  (`git status -s` output), and `no repos found` prints plain text instead of `[]`.
- **Suggested fix:** in JSON mode, send non-JSON messages to stderr (`Console(stderr=True)`), or reject the
  interactive flags together with `--json`.

### B4: `--inspect-timeout` is per git command, not per repo
- **Where:** `cli.py:39` help text and README; `inspect.py:49-57` applies `timeout` to each `_run`.
- **Symptom:** `inspect_repo` runs up to 8 git commands, plus up to 4 more with `--upstream-status`. At the
  CLI default of 10 s, one hung repo can block for about 2 minutes, and repos are inspected one at a time.
- **Suggested fix:** correct the help text and README, or enforce a real per-repo deadline.

### B5: README is out of date
- README says the `--inspect-timeout` default is 5; the CLI default is 10.0 (`cli.py:38`). (`inspect_repo`'s
  own default is 5.0, which may be the source of the confusion.)
- README leaves out `--upstream-status` and `--remote-status`, and does not mention that `--pull-clean` skips
  repos with more than one remote.
- **Suggested fix:** update README. Docs only; planned as step 2.

### B6: an unguarded `int()` parse can crash the whole run
- **Where:** `inspect.py:192-193`. `int(parts[0])` has no `ValueError` guard, while the equivalent code in
  `upstream_status` (`inspect.py:89-93`) has one. `ValueError` is not in `inspect_repo`'s `except` list, so it
  would escape `inspect_repo` and crash `gitrep`, not just mark that repo with an error.
- **Likelihood:** very low; git always prints two integers here. It is listed for consistency.
- **Suggested fix:** treat it as an error on that repo, like the other failures.

### B7: minor items
- `--workers 0` or a negative value is accepted and silently clamped to 1 (`fetch.py:66`).
- `--pull-clean` ignores `git pull` failures: the exit code is always 0 (`cli.py:165-167`).
- `git pull` and `git status -s` in `cli.py` have no timeout, so a credential prompt or hung remote blocks
  forever. (`git fetch` has a timeout.)
- `discover_repos` never returns bare repos (they have no `.git` inside), so the `bare` handling in
  `inspect_repo` and `render_table` can't be reached through the CLI. That code is only usable through the
  library API. This is an observation, not necessarily a bug.

### B8: `render_table` treats `root=""` inconsistently (found in Phase 2)
- **Where:** `report.py`. The title uses `if root:`, but the repo column uses `root is None`.
- **Symptom:** `render_table(..., root="")` gives a title with no root suffix, while paths are shown relative
  to the current directory. The CLI always passes a non-empty root, so it is unaffected.
- **Suggested fix:** use `if root:` in both places.

## What changed per module

All CLI output was checked end to end. I ran 10 flag combinations (table, `--all`, a real fetch,
`--json` with and without extras, `--include-submodules`, `--show-diff`, `--pull-clean` with `n` on stdin,
`--help`, a missing root) against a scratch repo tree, using both a `9e0809b` worktree and the branch head.
Stdout, stderr, and exit codes were **byte-identical**.

- **`_git.py` (new, private):** `git_argv`, `GIT_ERRORS`, `describe_error`. These replace four hand-built
  argv lists and two copies of the exception-to-message mapping.
- **`discovery.py`:** 42 → 23 lines. Inlined the one-line helpers; dropped the dead `is_file` branch, the
  redundant `exists()` check, and the default `os.walk` arguments. The docstring now states the pruning
  behavior (B1).
- **`fetch.py`:** 76 → 53 lines. `_fetch_one` has one error return. Removed the unreachable
  `CancelledError`/`BrokenExecutor` handler. `fetch_all` is a dict comprehension.
- **`inspect.py`:** one `_left_right_counts` parser replaces two copies; it still raises `ValueError` in
  `inspect_repo` (B6 pinned). Added `_read_head`, `_read_tracking`, `_count_lines`, and `_UPSTREAM_FIELDS`.
  The two swallowing excepts are merged; `base` is renamed to `status`. The `inspect_repo` docstring
  documents that the timeout applies per command. Complexity of `inspect_repo`: 16 → 9.
- **`report.py`:** added `_select` (shared by table and JSON), `_note`, and `_count_cell`. The `Path` import
  moved to the top. Added docstrings. `render_table` complexity: 11 → 7.
- **`cli.py`:** `main` is split into `_render`, `_show_diff`, and `_pull_clean`. Complexity of `main`: 16 → ≤7
  (the largest function in `cli.py` is now `_pull_clean`, at 8). Added type hints.
- **Tooling:** ruff config (py310; E/F/W/I/B/UP/SIM/RUF/C4/PIE/RET), `mypy --strict` on `src/`, and dev
  extras (`mypy`, `pytest-cov`, `ruff`). The lint CI now also runs `ruff format --check` and `mypy`. Added
  `environment.yml`.
- **README:** corrected the `--inspect-timeout` default and meaning, and documented `--upstream-status`,
  `--remote-status`, and the `--pull-clean` eligibility rules.
- **Tests (all approved entries):** P1 (untracked `.pyc` files); T1–T5 (66 new tests, including golden
  output snapshots in `tests/data/`); P2–P7 (cleanups with unchanged test and assert counts).

## Smells deliberately left alone

- **B1–B8 behavior issues:** left unfixed on purpose; each needs its own fix commit. B2 (fetch failures
  hidden) and B3 (non-JSON text in `--json`) are the most user-visible. See "Proposed breaking changes" in
  REFACTOR_PLAN.md.
- **`--inspect-timeout` help text** still says "per-repo" (B4), because `--help` output is frozen. The README
  and docstring are now correct.
- **The inspect timeout defaults disagree:** 5.0 in `inspect_repo`/`upstream_status` and 10.0 in the CLI.
  Changing either would change behavior.
- **`upstream_status` returns a bare 4-tuple.** Tests unpack it; the `NamedTuple` idea is still listed as a
  proposed change.
- **The argparse defaults (`/code`, 16, 30.0, 10.0) are inline literals.** Each is used once, so constants
  would add indirection without removing duplication.
- **`print()` for JSON in `cli._render`:** intentional, because rich must not re-highlight JSON. There is no
  print-as-logging anywhere, so no `logging` was added.
- **`inspect._run` vs `fetch._fetch_one`:** both call `subprocess.run`, but fetch needs the raw
  `CompletedProcess` and its own timing, so they were not merged.
- **Source line count went up (626 → 646)** even though the statement count went down (333 → 319). The
  increase is docstrings and small named helpers.
- **The golden tests depend on rich's rendering.** A rich upgrade may require regenerating them with
  `GITREP_REGEN_GOLDEN=1`, after confirming the diff is only cosmetic.

## Before / after numbers

| metric | before (`9e0809b`) | after |
|---|---|---|
| src lines (`wc -l`) | 626 | 646 |
| src statements | 333 | 319 |
| test lines | 1299 | 1779 |
| tests | 76 passed | 142 passed |
| coverage (line+branch) | 88% | 99% (the only miss is `if __name__ == "__main__"`) |
| `ruff check` (default rules) | 0 | 0 |
| `ruff check` (new stricter config) | 7 (tests) | 0 |
| `ruff format --check` | clean | clean |
| `mypy` (default) | 0 | 0 |
| `mypy --strict` | 2 | 0 |
| max cyclomatic complexity | 16 (`cli.main`, `inspect_repo`) | 9 (`inspect_repo`) |

## `git diff 9e0809b -- tests/`

This is **not empty**, by approval. Every change maps to an approved entry in TEST_CHANGE_PROPOSALS.md:
- P1: 6 `.pyc` files deleted from the index.
- T1–T5: added `test_fetch_errors.py`, `test_inspect_errors.py`, `test_cli_extra.py`,
  `test_report_notes.py`, `test_report_golden.py`, and `tests/data/*`.
- P2–P7: `conftest.py`, `test_cli.py`, `test_discovery.py`, `test_fetch.py`, `test_inspect.py`, and
  `test_report.py` were modified.

No test was skipped, xfailed, deleted, or loosened. P3 tightened an assertion. `[tool.pytest]` is unchanged.
Every `refactor(...)` commit touches only `src/`, not tests.
