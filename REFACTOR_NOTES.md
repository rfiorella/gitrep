# Refactor notes — gitrep

Baseline commit: `9e0809b`. This file is filled in during Phase 2; the wrap-up sections are still empty.

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

## What changed per module
_(Phase 2)_

## Smells deliberately left alone
_(Phase 2)_

## Before / after numbers

| metric | before (`9e0809b`) | after |
|---|---|---|
| src lines (`wc -l`) | 626 | |
| src statements | 333 | |
| tests | 76 passed | |
| coverage (line+branch) | 88% | |
| `ruff check` (default rules) | 0 | |
| `ruff format --check` | clean | |
| `mypy` (default) | 0 | |
| `mypy --strict` | 2 | |
| max cyclomatic complexity | 16 (`cli.main`, `inspect_repo`) | |
