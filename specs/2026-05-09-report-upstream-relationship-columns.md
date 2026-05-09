---
spec_id: ANALYSIS-2026-05-09-report-upstream-relationship-columns
spec_type: analysis
spec_version: 1
title: Add upstream-relationship columns to gitrep report
created: 2026-05-09
author: Rich Fiorella
project: gitrep

inputs:
  source_files:
    - path: /Users/rfiorella/code/gitrep/src/
      description: Existing gitrep source (discovery, inspection, report modules).
    - path: /Users/rfiorella/code/gitrep/tests/
      description: Existing test suite.
  data:
    - path: /code
      description: Root directory scanned for git repositories (same as foundational spec).
  baseline: null

deliverables:
  - Extended gitrep CLI with a new `--upstream-status` flag.
  - Four additional columns in the rich text table report (ahead/behind vs upstream master, ahead/behind vs upstream same-name branch) when flag is set.
  - Extended JSON output schema with the same four values as additional keys per repo entry when flag is set.
  - Tests covering upstream-status lookup (hit, miss, detached HEAD, no remote).

success_criteria:
  - id: sc1
    phase: implementation
    description: "`--upstream-status` flag is accepted by CLI without error when no repos are present."
    type: shell
    command: "mkdir -p /tmp/gitrep-empty-sc1 && gitrep --upstream-status --all --no-fetch --root /tmp/gitrep-empty-sc1 2>&1; echo exit=$?"
    assertion: "exit code is 0 or a known no-repo message; no unrecognised-argument error"
  - id: sc2
    phase: testing
    description: "Ahead/behind counts vs origin/HEAD (upstream master) match raw `git rev-list --left-right --count` output for a fixture repo."
    type: shell
    command: "pytest tests/ -k upstream_master -v"
    assertion: "all tests pass"
  - id: sc3
    phase: testing
    description: "Ahead/behind counts vs upstream same-name branch match raw `git rev-list --left-right --count` output for a fixture repo that has the branch on origin."
    type: shell
    command: "pytest tests/ -k upstream_same_name -v"
    assertion: "all tests pass"
  - id: sc4
    phase: testing
    description: "When the upstream same-name branch does not exist on origin, the four upstream-same-name cells are blank (not an error) in both rich and JSON output."
    type: shell
    command: "pytest tests/ -k upstream_missing -v"
    assertion: "all tests pass"
  - id: sc5
    phase: integration
    description: "`--json --upstream-status` output for a real repo under /code contains the four expected keys (upstream_master_ahead, upstream_master_behind, upstream_same_name_ahead, upstream_same_name_behind)."
    type: shell
    command: "gitrep --json --upstream-status /code | python3 -c \"import sys,json; data=json.load(sys.stdin); repo=data[0]; assert all(k in repo for k in ['upstream_master_ahead','upstream_master_behind','upstream_same_name_ahead','upstream_same_name_behind'])\""
    assertion: "no AssertionError; exit 0"
  - id: sc6
    phase: integration
    description: "Without `--upstream-status`, JSON output schema is unchanged (no new keys present)."
    type: shell
    command: "gitrep --json /code | python3 -c \"import sys,json; data=json.load(sys.stdin); repo=data[0]; assert 'upstream_master_ahead' not in repo\""
    assertion: "no AssertionError; exit 0"
  - id: sc7
    type: human-review
    phase: integration
    description: >
      After running `gitrep --upstream-status /code` against a representative set
      of real repos, a human visually inspects the rich table and confirms:
      columns "vs master (A/B)" and "vs same-name (A/B)" are present and
      aligned, missing upstream-same-name cells render as empty (no `None`,
      no dash), and integer counts look plausible for the repos inspected.

out_of_scope:
  - Fetching from any remote other than `origin`.
  - Comparing against remotes beyond `origin` (e.g., `upstream` fork remotes).
  - Automatically pulling or rebasing when behind upstream.
  - Showing diff content (commit log, patch) for the upstream gap.
  - Configurable remote name (hardcoded `origin` for this increment).
  - Any new mutating git operations beyond what the foundational spec already gates.

resolved_decisions:
  - Remote: hardcoded `origin` for this increment.
  - Upstream master detection: auto-detect via `git rev-parse --abbrev-ref origin/HEAD`; fall back to blank if origin/HEAD is not set.
  - Upstream same-name: `origin/<current-branch>`; if that ref does not exist, leave cells blank — not an error.
  - Fetch behaviour: `--upstream-status` reads cached refs by default; combine with existing `--fetch` flag to force a fresh fetch before inspection.
  - Output format: four new columns in rich table; four new JSON keys per repo entry; both gated on `--upstream-status`.
  - CLI flag name: `--upstream-status`.
  - JSON key names: `upstream_master_ahead`, `upstream_master_behind`, `upstream_same_name_ahead`, `upstream_same_name_behind`. Blank fields serialise as `null` in JSON.
  - Column labels in rich table: "vs master (A/B)" and "vs same-name (A/B)" where A=ahead, B=behind.

ask_before:
  - Changing the JSON key names from those listed in resolved_decisions.
  - Adding any fetch/pull side effect beyond what the existing `--fetch` flag already performs.
  - Expanding to support remotes other than `origin`.

execution:
  mode: checkpoint
  checkpoints:
    - after: planning
      requires: user-confirmation
    - after: implementation
      requires: tests-pass
    - after: testing
      requires: user-confirmation
    - after: integration
      requires: user-confirmation
  max_iterations_per_phase: 5
  parallelization:
    allowed: true
    max_subagents: 3
    plan: |
      The per-repo upstream lookup is independent across repos and fits
      naturally into the existing ThreadPoolExecutor used by the inspection
      module. No new parallelization infrastructure is needed; upstream
      queries (two `git rev-list` calls per repo) run inside the same
      worker that already handles ahead/behind vs origin.

      Implementation subtasks that can proceed in parallel after the
      planning checkpoint:
        1. Extend inspection module with upstream-status query function.
        2. Extend rich table formatter with the two new column pairs.
        3. Extend JSON serialiser with the four new keys.
        4. Write fixture-based tests for all four success-criteria test cases.

post_completion_review:
  enabled: false
  reviewers: []
  blocking: false

analysis_specific:
  language: python
  environment: gitrep
  test_strategy: test-along
  manifest_required: false
  performance_budget: null
  output_type: script
---

# Add upstream-relationship columns to gitrep report

## Context

The foundational `gitrep` tool (see References) already reports each
repo's relationship to its own tracking branch (ahead/behind `@{u}`).
That is useful for knowing whether a local branch needs pushing or
pulling relative to the branch it tracks. It does not show how the
local branch relates to the canonical state of the upstream project —
specifically, whether the local branch has diverged from upstream's
default branch (`origin/HEAD`, typically `master` or `main`) or from
the same-named branch on `origin`.

This spec extends the report with four additional integer values per
repo, exposed via a new `--upstream-status` flag:

- How many commits the local branch is ahead of `origin/HEAD`.
- How many commits the local branch is behind `origin/HEAD`.
- How many commits the local branch is ahead of `origin/<branch>` (if
  that ref exists).
- How many commits the local branch is behind `origin/<branch>` (if
  that ref exists).

This gives a clearer picture of contribution readiness: a branch that
is 0 behind `origin/HEAD` and 3 ahead is cleanly ready to propose as a
PR; one that is 15 behind needs a rebase first.

## Approach

Follows `python-analysis-conventions` (mamba env `gitrep`, test-along,
no reproducibility manifest — utility tool).

All git operations use `subprocess` (matching existing conventions).
Upstream-status queries are read-only.

Decomposition:

1. **Upstream query function** — given a repo path and current branch
   name, run:
   - `git rev-parse --abbrev-ref origin/HEAD` to find upstream master
     ref (e.g., `origin/main` or `origin/master`). Cache per-call;
     graceful blank on failure.
   - `git rev-list --left-right --count <upstream-master>...HEAD` →
     (behind, ahead) vs upstream master.
   - Check whether `origin/<branch>` ref exists (`git rev-parse
     --verify origin/<branch>`). If yes, run `git rev-list
     --left-right --count origin/<branch>...HEAD` → (behind, ahead) vs
     same-name. If no, return `(None, None)`.
   - Integrate into the per-repo inspection worker; no new thread pool
     needed.

2. **Rich table extension** — when `--upstream-status` is active, add
   two column pairs to the existing table: "vs master (A/B)" and "vs
   same-name (A/B)". Blank cells rendered as empty string (not `-`).

3. **JSON extension** — when `--upstream-status` is active, emit four
   additional keys per repo object: `upstream_master_ahead`,
   `upstream_master_behind`, `upstream_same_name_ahead`,
   `upstream_same_name_behind`. Missing/inapplicable values serialise
   as `null`.

4. **Tests** — pytest, fixture repos created via `git init` + scripted
   commits (same pattern as foundational spec). Cover:
   - Normal hit (upstream master and same-name both exist).
   - Same-name branch absent on origin.
   - `origin/HEAD` not configured (graceful blank).
   - Detached HEAD (no current branch name → same-name cells blank).

## Parallelization plan

Per-repo upstream lookups run inside the existing `ThreadPoolExecutor`
worker alongside the other inspection calls. No structural change to
concurrency model is required.

Implementation subtasks executable in parallel after planning
checkpoint:
1. Extend inspection module (`upstream_status()` function).
2. Extend rich table formatter.
3. Extend JSON serialiser.
4. Write tests (fixture repos + parametrized cases).

## References

- Foundational spec: `/Users/rfiorella/code/gitrep/specs/2026-05-08-multi-repo-manager.md`
- `git rev-list --left-right --count` for ahead/behind counts.
- `git rev-parse --abbrev-ref origin/HEAD` for upstream master detection.
- `git rev-parse --verify <ref>` for existence check of same-name branch.
- `rich.table.Table` for output formatting.
