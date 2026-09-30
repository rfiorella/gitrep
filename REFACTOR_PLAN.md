# Refactor plan — gitrep

Baseline commit: `9e0809b` (main, clean tree). Status: **Phase 1 — awaiting approval. No code changed.**

Related files: `REFACTOR_NOTES.md` (bugs found, not fixed), `TEST_CHANGE_PROPOSALS.md`
(proposed characterization tests and test cleanups, none applied).

---

## 1. Package map

`src/gitrep/` — 626 lines of source in total (`wc -l`), 333 statements.

| module | lines | job | depends on |
|---|---|---|---|
| `__init__.py` | 11 | Re-exports public API (`__all__`: `FetchResult`, `RepoStatus`, `discover_repos`, `fetch_all`, `inspect_repo`) | discovery, fetch, inspect |
| `discovery.py` | 42 | `os.walk` a root, return sorted dirs holding a `.git` dir (optionally a `.git` file); prune at each repo | stdlib |
| `fetch.py` | 76 | `FetchResult` dataclass; `git fetch --all --prune --quiet` per repo in a `ThreadPoolExecutor`; errors become `ok=False` results | stdlib |
| `inspect.py` | 217 | `RepoStatus` dataclass + `to_dict`/`needs_attention`; `_run` git helper; `upstream_status()` (ahead/behind vs `origin/HEAD` and `origin/<branch>`); `inspect_repo()` (runs 5–8 git commands and fills in `RepoStatus`) | stdlib |
| `report.py` | 105 | `filter_attention`, `render_table` (rich `Table`), `render_json`, `_relpath`, `_ab_cell` | inspect, rich |
| `cli.py` | 175 | argparse parser; `main()` runs discover → fetch → inspect → render, then the optional `--show-diff` and `--pull-clean` (interactive) | discovery, fetch, inspect, report, rich |

```
cli ──► discovery
  ├──► fetch
  ├──► inspect ◄── report
  └──► report
```

No cycles. Nothing uses `logging`. The one `print` (`cli.py:117`) writes JSON to stdout, which is correct CLI
output, so no print-to-logging conversion is needed.

### Constraints the tests put on the code (must be preserved)

These are not in `__all__`, but the tests import or monkeypatch them, so they are effectively frozen:

- `gitrep.inspect.upstream_status(path, *, branch, timeout=5.0)` must return a 4-tuple.
- `gitrep.report.filter_attention`, `render_table`, `render_json`, including their keyword names.
- `gitrep.cli._build_parser`, `gitrep.cli._confirm(prompt)`.
- `cli` must look up `discover_repos`, `fetch_all`, and `inspect_repo` as **module globals at call time**, and
  must call them with exactly these keywords: `discover_repos(root, skip_submodules=)`,
  `fetch_all(repos, max_workers=, timeout=)`, `inspect_repo(p, timeout=, with_upstream=)`.
- `cli` must run git via `subprocess.run` looked up on the `subprocess` module (`cli_mod.subprocess.run` is
  patched).
- Output order in `--pull-clean`: the target block, then the skip block, then the confirmation prompt.

---

## 2. Baseline

Environment: mamba env `gitrep`, Python 3.12.13, git 2.56.0. The env has **no** pytest-cov, ruff, or mypy, so
I ran them ephemerally with `uvx` / the base ruff and did **not** install them into the env (see Open questions).

| check | result |
|---|---|
| `pytest` | **76 passed**, 0 failed/skipped (15.2 s) |
| `ruff check .` (0.15.17, default rules, no config in repo) | All checks passed |
| `ruff format --check .` | 12 files already formatted |
| `mypy src` (not configured; defaults) | Success, 0 issues |
| `mypy --strict src` | 2 errors: `report.py:81` and `cli.py:72` (untyped params) |

Coverage (`pytest --cov=gitrep --cov-branch`):

| module | stmts | miss | branch | partial | cover | missing |
|---|---|---|---|---|---|---|
| `__init__.py` | 4 | 0 | 0 | 0 | 100% | |
| `cli.py` | 78 | 10 | 32 | 2 | 85% | 84-88 (`_confirm`), 137-140 (`--show-diff`), 175 |
| `discovery.py` | 30 | 0 | 12 | 0 | 100% | |
| `fetch.py` | 36 | 8 | 4 | 0 | 80% | 38-49 (all exception paths), 72-73 |
| `inspect.py` | 122 | 14 | 42 | 8 | 87% | 85, 88, 92-93 (parse guards), 113-117, 210-215 (all exception paths) |
| `report.py` | 63 | 5 | 22 | 3 | 91% | 50, 54, 56 (error/detached/bare notes), 86-87 |
| **total** | 333 | 37 | 112 | 13 | **88%** | |

**Pattern:** the happy paths are well covered. **Every exception-handling branch in `fetch.py` and `inspect.py`
is untested**, as are `_confirm`, `--show-diff`, and three of the four note values in the table.

Extended ruff survey (`--select E,F,W,I,B,UP,SIM,RUF,PL,C90,ARG,RET,PIE,T20`, informational only):
C901 in `cli.main` (16), `inspect_repo` (16), `upstream_status` (11), `render_table` (11); PLR0912/0915 in
`main` and `inspect_repo`; PLR2004 (`2`) at `inspect.py:87,191`; PLC0415 at `report.py:83`; T201 at
`cli.py:117` (intentional).

---

## 3. Code smells

### Duplicated / near-duplicate code
- **The `rev-list --left-right --count` output is parsed twice**: `inspect.py:80-94` (`_ab`, guards against
  `ValueError`) and `inspect.py:184-193` (inline, *no* `ValueError` guard; see REFACTOR_NOTES B6). Both also
  check `len(parts) != 2`, the magic `2`.
- **The git error-to-message mapping is copied** between `fetch.py:38-53` and `inspect.py:210-215`: the same
  three branches build `"timeout after {t}s"`, `"git not found: {e}"`, and `"{type(e).__name__}: {e}"`.
- `["git", "-C", str(path), ...]` is built in 4 places: `fetch.py:26`, `inspect.py:51`, `cli.py:140`,
  `cli.py:166`.
- `fetch.py:33-53`: the `FetchResult(...)` construction is repeated in 4 branches that differ only in
  `ok`/`stderr`.
- The upstream field names are spelled out in `inspect.py:34-37` and again as dataclass fields (`22-25`).
- `report.py:29` and `report.py:97`: the same `rows = list(...) if show_all else filter_attention(...)`.

### Dead / redundant code
- `discovery.py:7-13`: `_is_repo_root` has an `if git.is_file(): return False` branch that falls through to
  `return False`. It reduces to `(p / ".git").is_dir()`.
- `discovery.py:16-18`: a one-line helper used once.
- `discovery.py:25-26`: `if not root.exists(): return found` is redundant, because `os.walk` on a missing path
  yields nothing.
- `discovery.py:29`: `followlinks=False` and `onerror=lambda _e: None` are both `os.walk` defaults (the default
  already ignores errors).
- `discovery.py:40`: `d not in {".git"}` uses a one-element set literal.
- `fetch.py:72-75`: catches `CancelledError`/`BrokenExecutor`. Nothing cancels futures, and there is no pool
  initializer to break the pool, so this is unreachable (uncovered).
- `fetch.py:63-64`: an early return for empty `repos`. It is redundant (a 1-worker pool with no work also
  returns `{}`), but it is cheap and clear. **Leave as-is.**
- `inspect.py:113-117`: two `except` clauses that both `pass`. They can be one tuple.
- `inspect.py:39`, `41`: `d.pop(k, None)`. The keys always exist in `asdict`, so the default is dead (harmless).
- `inspect.py:177`: `_out, _err` are unused bindings.
- `tests/conftest.py:54` `git_env_extra` fixture is unused (tests are read-only; see TEST_CHANGE_PROPOSALS).

### Over-defensive code / swallowed errors
- **`cli.py:107` throws away the result of `fetch_all()`.** All the careful `ok=False, stderr=...` handling in
  `fetch.py` never reaches the user. This is a behavior issue, not only style (REFACTOR_NOTES B2).
- `inspect.py:96-117`: `upstream_status` silently turns timeouts and OS errors into `None`s. That is documented
  and intentional, so keep it.
- Converting exceptions into return values (`FetchResult.ok`, `RepoStatus.error`) is a deliberate design choice
  (one bad repo must not abort the batch). Keep it.

### Needless abstractions
- There are few. `_is_submodule_marker` and `_is_repo_root` are one-line wrappers. The `_ab` closure inside
  `upstream_status` would be clearer as a module-level helper shared with `inspect_repo`.
- No needless classes, factories, or managers.

### Comments and docstrings
- `cli.py:72-73`: the docstring is accurate but no clearer than the code.
- `inspect.py:97`, `104`, `114`: comments that say what the code does ("leave any unresolved fields as None").
- `inspect.py:200-202`: a *why* comment, but it is partly wrong. For a detached HEAD, `branch` holds the short
  SHA, and the comment explains that. Keep a shorter version.
- `fetch.py:62` and `discovery.py:22` docstrings: accurate.
- **Wrong:** the `--inspect-timeout` help text (`cli.py:39`) and README both say "per-repo". The timeout is
  actually **per git command**, and there are up to 12 commands per repo (B4).
- **Wrong:** README says the `--inspect-timeout` default is 5; the code says 10 (`cli.py:38`). README also
  leaves out `--upstream-status`, `--remote-status`, and the single-remote rule for `--pull-clean` (B5).
- Several public functions have no docstring: `render_table`, `render_json`, `filter_attention`,
  `RepoStatus.to_dict`, `needs_attention`.

### Naming / magic numbers
- `inspect.py`: the variable holding the result is called `base` (it is the status being built). The
  `rc, out, err` / `rc2, out2` tuples shadow each other.
- `cli.py`: `s`/`p` for statuses and paths. That is OK in comprehensions but hard to scan in the 80-line
  `main`.
- Magic `2` (`inspect.py:87,191`). The defaults `16`, `30.0`, `10.0`, `"/code"` appear only once each in
  argparse, which is fine. The inspect timeout defaults to `5.0` in `inspect_repo`/`upstream_status` but to
  `10.0` in the CLI, which is inconsistent (behavior, so leave it; noted).

### Long functions / mixed responsibilities
- `cli.main` (80 lines, CC 16) handles arg validation, the pipeline, rendering, `--show-diff`, and the whole
  interactive `--pull-clean` flow.
- `inspect_repo` (95 lines, CC 16) runs 8 git queries in a row inside one `try`.

### Type hints
- `cli._pull_clean_base_eligible(s)` and `report._relpath(p, root)` have untyped parameters (the only
  `mypy --strict` errors).
- `upstream_status` returns a bare 4-tuple of `int | None`. A `NamedTuple` would self-document (see Proposed
  breaking changes; it is technically compatible).
- `render_table(..., root: str | None)`, but `cli` passes `str(root)` of a `Path`. `Path | str` would be more
  honest.

### Imports
- `report.py:83`: `from pathlib import Path` inside a `try` inside a function.

### Dependencies / config / tooling
- Runtime dependency `rich` is declared and used. `pytest-timeout` is declared and used (`timeout = 60`).
- **Used but not declared:** `ruff` (CI installs it ad hoc). There is no mypy config and no coverage tooling in
  `dev`.
- There is no ruff config. CI runs `ruff check` but not `ruff format --check`.
- There is no `environment.yml`, although README and CLAUDE.md name the mamba env `gitrep`. That is a
  reproducibility gap.
- `requires-python >=3.10`, but CI tests only 3.12.
- `tests/__pycache__/*.pyc` (6 files) are **tracked in git** despite `.gitignore` (proposal P1).
- `.claude/project-config.yml` is tracked although `.claude/` is gitignored. It is harmless; noting it only.

---

## 4. Proposed steps (lowest → highest risk)

All test runs use `PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider`. Otherwise pytest rewrites the
`.pyc` files tracked under `tests/__pycache__/` and `git diff -- tests/` stops being empty (this happened
once during the survey and was reverted with `git checkout`).

Each step is one commit. After every step: `pytest`, `ruff check`, `ruff format --check`, `mypy src` (and
`--strict` once step 1 lands). "Coverage" means how well the touched lines are tested at baseline.

| # | step | files | coverage of touched code | risk |
|---|---|---|---|---|
| 0 | `chore(tooling)`: add `[tool.ruff]` (target py310, line 88, `select = E,F,W,I,B,UP,SIM,RUF,C4,PIE,RET`) and `[tool.mypy] strict = true, files = src`; add `ruff`, `mypy`, `pytest-cov` to the `dev` extra; add `ruff format --check` and `mypy` to the lint workflow. No `[tool.pytest]` change. | `pyproject.toml`, `.github/workflows/lint.yml` | n/a | low (**needs approval: adds dev deps**) |
| 1 | `refactor(types)`: annotate `_pull_clean_base_eligible(s: RepoStatus)` and `_relpath(p: Path, root: str)`; move the `Path` import to module top in `report.py`. Makes `mypy --strict` clean. | `cli.py`, `report.py` | cli line covered; `_relpath` fallback 86-87 **uncovered** (the change there is import-only) | low |
| 2 | `docs`: fix README (inspect-timeout default 10; add `--upstream-status`, `--remote-status`, and the `--pull-clean` single-remote rule). Docstrings for the public `report`/`RepoStatus` functions. No help-text change (see Open questions). | `README.md`, `report.py`, `inspect.py` | n/a | low |
| 3 | `refactor(discovery)`: collapse `_is_repo_root`/`_is_submodule_marker` into inline `.is_dir()`/`.is_file()` checks; drop the redundant `exists()` check and the default `os.walk` args; `d != ".git"`. | `discovery.py` | **100%** line+branch | low |
| 4 | `refactor(inspect)`: add module-level `_left_right_counts(path, ref, timeout) -> tuple[int, int] \| None` (it raises `ValueError` on non-int output, so it keeps each caller's current behavior: `upstream_status` catches it, `inspect_repo` does not). Use it in both places; name the `2`; add a module constant for the upstream field names used in `to_dict`; merge the two `pass` excepts; rename `base` → `status`. | `inspect.py` | main paths covered; parse guards 85/88/92-93 and excepts 113-117 **uncovered** | medium |
| 5 | `refactor(inspect)`: split `inspect_repo` into small private readers (`_read_head`, `_read_tracking`, `_count_lines`) called inside the **unchanged** outer `try`/`except`. | `inspect.py` | readers well covered; outer except 210-215 **uncovered but not modified** | medium |
| 6 | `refactor(report)`: share the row selection between table and JSON; pull the note-cell logic into `_note(s)`. | `report.py` | table/JSON covered; note branches 50/54/56 **uncovered** | **high risk**: wants characterization test T4 first |
| 7 | `refactor(cli)`: split `main` into `_render(statuses, args, root, console)`, `_show_diff(...)`, `_pull_clean(...)`. Keep all the test-coupling constraints in §1. | `cli.py` | pipeline and `--pull-clean` covered; `--show-diff` 137-140 and `_confirm` 84-88 **uncovered** | **high risk**: wants T3 first |
| 8 | `refactor(git)`: add a private `_git.py` with `git_argv(path, *args)` and `describe_error(exc, timeout) -> str`, used by `fetch.py` and `inspect.py` (and `git_argv` by `cli.py`); collapse `_fetch_one` into a single `FetchResult(...)` return. Old names stay where they are. | new `_git.py`, `fetch.py`, `inspect.py`, `cli.py` | **all exception paths uncovered** (fetch 38-49, inspect 210-215) | **high risk**: wants T1, T2 first |
| 9 | `refactor(fetch)`: delete the unreachable `CancelledError`/`BrokenExecutor` handler. | `fetch.py` | **uncovered** (72-73) | **high risk**: the behavior is unobservable in practice, but I'd like explicit OK |

Steps 0–5 can run without further approval once the plan is approved (step 0 needs the dev-dependency OK).
For 6–9, I will pause and check in, and I'd prefer the matching characterization tests in
TEST_CHANGE_PROPOSALS.md (T1–T4) to be approved and landed first, in their own `test:` commits.

Not planned, deliberately: converting to `logging` (no print-as-logging exists); adding constants for the
argparse defaults (each is used once); changing the exception-to-result design; any change to CLI text.

---

## Proposed breaking changes

None of these will be done without your OK. Most are really behavior fixes. See REFACTOR_NOTES for details.

1. **Show fetch failures** (B2): use the `fetch_all` results and add a note such as `fetch failed: <stderr>`,
   and/or count a failed fetch toward `needs_attention`. This changes table/JSON output.
2. **Keep `--json` stdout pure JSON** (B3): send the human-readable messages (`no repos found`, the
   `--pull-clean` and `--show-diff` output) to stderr when `--json` is set. Alternatively, reject
   `--json --pull-clean`.
3. **`--include-submodules`** (B1): either make it find real submodules (descend into a repo's worktree only
   to find `.git` files) or rename/re-document it. Right now it only finds orphaned gitlink dirs.
4. **Help text for `--inspect-timeout`** (B4): change it to "per git command timeout". This is CLI output.
5. `upstream_status` → return a `NamedTuple` (`UpstreamStatus(master_ahead, ...)`). It still unpacks and
   compares equal to a tuple, but its type and `repr` change.
6. Export `filter_attention`, `render_table`, `render_json`, `upstream_status` from the top-level package.
   This is additive; it only grows the API.

## Open questions

1. **Dev tooling:** may I add `ruff`, `mypy`, and `pytest-cov` to `[project.optional-dependencies].dev` (and
   into the `gitrep` mamba env)? Should I also add an `environment.yml`? Until you decide, I'll keep running
   them through `uvx`.
2. **Ruff/mypy config:** do you accept the rule set in step 0 and `mypy --strict` on `src/`? The only
   violations today are the two fixed in step 1.
3. **Is `--help` text frozen as CLI output?** I'm treating it as frozen. That decides whether B4 goes into a
   refactor commit or a fix commit.
4. **Characterization tests T1–T5:** approve before steps 6–9?
5. **Tracked `.pyc` files under `tests/`** (P1): OK to `git rm --cached` them? This removes files under
   `tests/` from the index but changes no test source.
6. Should the CI test matrix include 3.10/3.11 to match `requires-python`?
