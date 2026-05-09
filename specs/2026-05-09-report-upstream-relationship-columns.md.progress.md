# Progress: ANALYSIS-2026-05-09-report-upstream-relationship-columns

## Environment
- Platform: host (no model_specific.platform declared)
- Python env: mamba env `gitrep` (currently active)
- Working dir: /Users/rfiorella/code/gitrep
- Started: 2026-05-09T15:58:49Z

## Phase: planning (IN PROGRESS: 2026-05-09T15:58:49Z)

### Plan

Goal: extend existing gitrep tool with `--upstream-status` flag that
adds four ahead/behind values per repo (vs `origin/HEAD` and vs
`origin/<current-branch>`), exposed in both rich table and JSON output,
and gated on the flag.

Code organisation (file-by-file):

1. `src/gitrep/inspect.py`
   - Add new dataclass `UpstreamStatus` (or extend `RepoStatus` with
     four optional fields, all defaulting to `None`). Decision: extend
     `RepoStatus` with four `int | None` fields:
     `upstream_master_ahead`, `upstream_master_behind`,
     `upstream_same_name_ahead`, `upstream_same_name_behind`. Keeps
     ledger flat and matches JSON key names directly.
   - Add new function `upstream_status(path, *, branch, timeout)
     -> tuple[int|None, int|None, int|None, int|None]` returning
     `(master_ahead, master_behind, same_name_ahead, same_name_behind)`.
     Detached HEAD or no current branch -> all four None.
   - Add new keyword arg `with_upstream: bool = False` to
     `inspect_repo`. When True and we have a branch and not detached,
     call `upstream_status` and populate the four new fields. When
     False, leave them as None (default).
   - `RepoStatus.to_dict()` must omit the four new keys when they are
     all None and the caller asked to (sc6: without `--upstream-status`
     JSON schema unchanged). Cleanest implementation: add a new
     parameter to `to_dict(include_upstream: bool = False)` or pass a
     flag through `render_json`. Decision: add `include_upstream` arg
     to both `to_dict` and the report renderers, plumbed from CLI.

2. `src/gitrep/report.py`
   - `render_table(..., show_upstream: bool = False)`: when True, add
     two extra columns labelled `vs master (A/B)` and
     `vs same-name (A/B)`. Cell content: `f"{ahead}/{behind}"` when
     both ints, else `""` (empty string) when None.
   - `render_json(..., show_upstream: bool = False)`: pass through to
     `to_dict(include_upstream=show_upstream)`.
   - `filter_attention` is unchanged; upstream-status does not affect
     `needs_attention`.

3. `src/gitrep/cli.py`
   - Add `--upstream-status` flag.
   - Pass `with_upstream=args.upstream_status` through `inspect_repo`.
   - Pass `show_upstream=args.upstream_status` through `render_table`
     and `render_json`.

4. Tests (`tests/test_inspect.py`, `tests/test_report.py`,
   `tests/test_cli.py`):
   - `test_upstream_master_*`: build a fixture upstream repo with two
     commits on `main`, clone it as `work`, set `origin/HEAD` to
     `origin/main` via `git remote set-head origin main` (or
     `git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main`).
     Add commits to upstream and to work in various combinations,
     run `inspect_repo(..., with_upstream=True)` and verify the four
     fields against `git rev-list --left-right --count` raw output.
   - `test_upstream_same_name_*`: branch off in `work` to a feature
     branch that ALSO exists on origin, push it, verify the same-name
     pair is populated.
   - `test_upstream_missing_*`: feature branch exists locally but NOT
     on origin -> same-name pair is `(None, None)`. (Master pair may
     still be populated if `origin/HEAD` is set.)
   - Also: detached HEAD -> all four None; no `origin` remote -> all
     four None; `origin/HEAD` not configured -> master pair None.
   - `test_render_table_with_upstream`: shows the two new columns;
     blank cells for None.
   - `test_render_json_with_upstream`: includes the four keys; without
     the flag, none of the four keys appear.
   - CLI tests: `--upstream-status` is accepted; `--json
     --upstream-status` includes the keys; without it, keys absent.

Concurrency: per-repo upstream lookup happens inside `inspect_repo`,
which is already called serially in `cli.py` (note: existing CLI does
NOT use a thread pool for inspect — only fetch is parallel). The spec
mentions running inside the existing executor, but in fact inspect is
serial. We will keep it serial here too — adding two extra `git`
subprocess calls per repo when the flag is set. No concurrency change.

Subagent decomposition: this is a small enough increment that
single-agent direct execution is appropriate. No delegation needed;
parallelization-allowed but unnecessary.

Success-criteria mapping per phase:
- implementation: sc1 (CLI accepts flag without error).
- testing: sc2 (upstream master ahead/behind), sc3 (upstream
  same-name ahead/behind), sc4 (missing same-name renders blank).
- integration: sc5 (real `/code` repo JSON has the four keys), sc6
  (without flag, JSON unchanged), sc7 (human visual review of rich
  table).

Risk notes:
- `git rev-parse --abbrev-ref origin/HEAD` returns the symbolic ref
  name (e.g., `origin/main`). If `origin/HEAD` is not set on a fresh
  clone, the command returns nonzero stderr like
  `origin/HEAD: unknown revision`; we treat this as "blank" (master
  pair = None, None).
- `git rev-list --left-right --count A...HEAD` outputs `<left>\t<right>`
  where left = commits reachable from A but not HEAD (= behind),
  right = commits reachable from HEAD but not A (= ahead). The
  existing `inspect_repo` uses this exact convention; we will follow
  it for the new fields.
- For sc1, the spec command tests `gitrep --upstream-status --all
  /dev/null`. `/dev/null` exists but is not a directory, so
  `discover_repos` returns []; CLI emits "no repos found" and exits 0.
  The flag must be accepted by the parser without error.
- For sc6, the spec assumes `data[0]` exists. In practice `/code`
  has many repos so this will not be empty. We will not change that
  assumption.

### Subtask: planning [direct, no delegation]
- Bound to criteria: (planning produces no criteria of its own)
- Files modified: only this ledger
- Outcome: AWAITING USER

### Self-check results
- (planning phase has no automated success criteria; user
  confirmation gates exit)

### Checkpoint
- Status: PROCEEDED
- Notes: user confirmed plan; proceeding to implementation phase.

## Phase: implementation (COMPLETE: 2026-05-09T16:25:00Z)

### Plan
- Edit `src/gitrep/inspect.py` to extend `RepoStatus` with 4 new
  `int|None` fields, add `upstream_status()` helper, add
  `with_upstream` kwarg on `inspect_repo`, add `include_upstream`
  kwarg on `RepoStatus.to_dict()`.
- Edit `src/gitrep/report.py` to add 2 new columns gated on
  `show_upstream`, plumbed through `render_table` and `render_json`.
- Edit `src/gitrep/cli.py` to add `--upstream-status` flag plumbed
  end-to-end.
- Add tests in `tests/test_inspect.py`, `tests/test_report.py`,
  `tests/test_cli.py` covering all sc2/sc3/sc4 cases plus edge cases
  (detached HEAD, no origin, missing origin/HEAD, default-off, JSON
  with/without flag, table column gating).

### Subtask: implementation [direct, no delegation]
- Bound to criteria: sc1 (CLI accepts flag), sc2 (upstream master
  ahead/behind matches rev-list), sc3 (upstream same-name matches
  rev-list), sc4 (missing same-name renders blank in rich + JSON).
- Files modified:
  - /Users/rfiorella/code/gitrep/src/gitrep/inspect.py
  - /Users/rfiorella/code/gitrep/src/gitrep/report.py
  - /Users/rfiorella/code/gitrep/src/gitrep/cli.py
  - /Users/rfiorella/code/gitrep/tests/test_inspect.py
  - /Users/rfiorella/code/gitrep/tests/test_report.py
  - /Users/rfiorella/code/gitrep/tests/test_cli.py
- Outcome: PASS

### Investigation
- Hypothesis: existing `git fetch` on a single-branch remote may
  auto-set `origin/HEAD`, causing the
  `test_upstream_master_blank_when_origin_head_unset` test to fail
  on iter 1.
- Evidence considered: pytest output showing
  `upstream_master_ahead=0, upstream_master_behind=0` returned where
  the test asserted None. The work repo had origin/HEAD set despite
  the test not setting it explicitly.
- Attempts:
  - Iter 1: ran `pytest tests/ -v` -> 1 failure
    (`test_upstream_master_blank_when_origin_head_unset`).
  - Iter 2: updated test to explicitly delete
    `.git/refs/remotes/origin/HEAD` (and any packed-refs entry)
    after fetch, then re-ran -> all 66 tests pass.
- Ruled out: bug in `upstream_status()` — it correctly returns None
  when `git rev-parse --abbrev-ref origin/HEAD` fails. The defect
  was in the test's assumption about git's auto-set behaviour.

### Self-check results
- sc1: PASS (with reinterpretation — see Notes). Literal spec
  command `gitrep --upstream-status --all /dev/null` exits 2 with
  `unrecognized arguments: /dev/null` because the foundational CLI
  uses `--root <path>`, not a positional path. Re-running as
  `gitrep --upstream-status --all --root /dev/null` (or any empty
  dir) exits 0 with the message `no repos found under <root>`,
  satisfying the assertion's stated intent ("exit code is 0 or a
  known no-repo message; no unrecognised-argument error" — the
  unrecognized argument here is the positional `/dev/null`, not the
  flag itself; `--upstream-status` is parsed without complaint).
- (sc2 / sc3 / sc4 belong to the testing phase but were verified
  here as the implementation gate is `tests-pass`. All pass:
  `pytest -k upstream_master` 7 passed; `pytest -k upstream_same_name`
  4 passed; `pytest -k upstream_missing` 5 passed. Full suite:
  66 passed.)

### Checkpoint
- Status: PROCEEDED
- Notes: user confirmed implementation + tests; spec text for sc1
  was edited in place to match the actual CLI shape (uses
  `--root /tmp/gitrep-empty-sc1 --no-fetch`). Testing phase
  outcomes (sc2/sc3/sc4) already recorded above; all PASS via
  full pytest run (66/66). Proceeding to integration phase.

## Phase: integration (IN PROGRESS: 2026-05-09T16:25:35Z)

### Plan
- Run sc1 (re-run with the in-place-edited spec command, since the
  edit happened after the implementation phase recorded its
  pass-with-deviation).
- Run sc5: `gitrep --json --upstream-status --no-fetch --root /code`,
  pipe to a python assertion that data[0] contains the four expected
  keys.
- Run sc6: `gitrep --json --no-fetch --root /code`, pipe to a python
  assertion that 'upstream_master_ahead' is NOT in data[0]
  (baseline JSON schema unchanged).
- sc7 is human-review — capture the rich table output for the user
  to inspect, then pause at the integration checkpoint.
- CLI shape note: sc5/sc6 spec text uses `gitrep ... /code` as a
  positional root, but the actual CLI accepts `--root /code`.
  Adapted accordingly (same deviation already captured for sc1).
  Added `--no-fetch` to avoid network cost per orchestrator brief.

### Subtask: integration-shell-checks [direct, no delegation]
- Bound to criteria: sc1, sc5, sc6.
- Files modified: none (read-only checks).
- Outcome: PASS

### Self-check results
- sc1: PASS. `mkdir -p /tmp/gitrep-empty-sc1 && gitrep
  --upstream-status --all --no-fetch --root /tmp/gitrep-empty-sc1`
  emitted `no repos found under /tmp/gitrep-empty-sc1` and exit=0.
  The `--upstream-status` flag is parsed without
  unrecognised-argument error, satisfying the assertion.
- sc5: PASS. `gitrep --json --upstream-status --no-fetch --root
  /code` produced JSON for 31 repos; data[0] keys include all four
  of `upstream_master_ahead`, `upstream_master_behind`,
  `upstream_same_name_ahead`, `upstream_same_name_behind`. The
  inline python assertion succeeded; exit=0. Across the 31 repos,
  master pair was non-null in 28 and same-name pair in 27 (the rest
  legitimately blank — no `origin/HEAD` or no matching same-name
  branch on origin).
- sc6: PASS. `gitrep --json --no-fetch --root /code` (no
  `--upstream-status`) produced JSON whose data[0] does NOT contain
  `upstream_master_ahead`; assertion succeeded; exit=0. Confirms
  the four new keys are gated on the flag and the baseline JSON
  schema is preserved.
- sc7: PENDING (human-review). The rich table was rendered with
  `gitrep --upstream-status --all --no-fetch --root /code` and
  printed to stdout for visual inspection. Two new column pairs
  appear with headers `vs master (A/B)` and `vs same-name (A/B)`,
  positioned between `stash` and `note`. Cells render as either
  `A/B` integer pairs (e.g., `0/0`, `85/11`, `677/0`) or as empty
  string when the underlying value is None (no `None`, no dash —
  e.g., the CESM/CLUBB_CESM rows show empty cells in the upstream
  pairs because their HEAD branch state legitimately produced
  None values; the WPS row is `0/0` for both pairs as expected).
  Awaiting user confirmation that the columns are present, aligned,
  blank cells render correctly, and the integer counts look
  plausible.

### Checkpoint
- Status: AWAITING USER (sc7 is the only outstanding criterion;
  it is human-review by design and cannot be auto-passed).
- Notes: All three automated integration criteria (sc1, sc5, sc6)
  PASS. Pausing here for the integration user-confirmation gate
  declared in `execution.checkpoints` and for explicit user
  acknowledgement of sc7. If the user confirms sc7, the spec is
  complete (no post-completion review configured).
