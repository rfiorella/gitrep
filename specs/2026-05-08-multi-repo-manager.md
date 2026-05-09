---
spec_id: ANALYSIS-2026-05-08-multi-repo-manager
spec_type: analysis
spec_version: 1
title: Multi-repo status & mass-fetch manager
created: 2026-05-08
author: Rich Fiorella
project: gitrep

inputs:
  source_files: []
  data:
    - path: /code
      description: Root directory scanned recursively for git repositories.
  baseline: null

deliverables:
  - Python script (CLI) that discovers all git repos under /code.
  - Parallel `git fetch` across all discovered repos.
  - Per-repo status summary: current branch, dirty/clean, ahead/behind origin, stash count.
  - Default report listing repos that are (a) behind origin on current branch, (b) have uncommitted changes.
  - Optional flags to act on findings (e.g., pull, stage/commit prompt) — list-only by default.

success_criteria:
  - Discovers all repos under /code without missing nested or sibling repos.
  - Mass fetch of 50 repos completes in under 60 seconds on reasonable network.
  - Status summary correctly classifies dirty / behind / stashed states (verified against `git status` and `git rev-list --count`).
  - Default invocation is read-only — no fetch/pull/commit side effects unless flags passed (fetch is the one explicit exception when invoked).
  - Tests pass (test-along).

out_of_scope:
  - Pushing, force-push, rebase, merge operations.
  - Automatic commit message generation.
  - Repo cloning / new-repo creation.
  - Non-git VCS (hg, svn).
  - GUI / TUI beyond `rich` console output.

resolved_decisions:
  - Language: Python.
  - Environment: mamba env `gitrep`.
  - Output formatting: `rich` for console tables / colored status.
  - Git interface: prefer `subprocess` over `gitpython` for portability and speed; revisit if logic gets gnarly.
  - Concurrency: `concurrent.futures.ThreadPoolExecutor` for parallel fetches (git is I/O-bound here).
  - Repo discovery: walk `/code` looking for `.git` directories; skip nested submodules.
  - Default mode: read-only listing; mutating actions gated behind explicit flags.

ask_before:
  - Adding any push/pull/commit action — confirm flag UX before wiring.
  - Adding config file (e.g., per-user repo allowlist/ignorelist) — confirm scope.
  - Adding non-`/code` search roots.

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
      Subtasks parallelizable at design time:
        1. repo discovery module
        2. git status/ahead-behind/stash inspection module
        3. parallel fetch driver
        4. report formatter (rich)
      Modules 1-3 implementable in parallel after interfaces agreed in planning.

post_completion_review:
  enabled: false
  reviewers: []
  blocking: false

analysis_specific:
  language: python
  environment: gitrep
  test_strategy: test-along
  manifest_required: false
  performance_budget:
    wall_time_seconds: 60
    dataset: 50 repos under /code, warm DNS, fetch over typical residential network
  output_type: script
---

# Multi-repo status & mass-fetch manager

## Context

Local `/code` directory holds many git repos. Manual tracking of which
are dirty, behind origin, or have stashed work is tedious. Goal: one
command that discovers every repo, fetches in parallel, and reports
actionable status (dirty / behind / stashed) so the user knows what
needs attention without `cd`-ing through dozens of directories.

## Approach

Follows `python-analysis-conventions` (env management via mamba,
test-along, no reproducibility manifest needed — utility tool, not
scientific analysis).

Decomposition:

1. **Discovery** — walk `/code`, find `.git` dirs, return list of repo
   paths. Skip submodule `.git` files (regular files, not dirs). Test
   with a fixture tree.
2. **Inspection** — per-repo, run `git` subprocesses to collect:
   - current branch (`git rev-parse --abbrev-ref HEAD`)
   - dirty state (`git status --porcelain`)
   - ahead/behind upstream (`git rev-list --left-right --count @{u}...HEAD`)
   - stash count (`git stash list | wc -l`)
   Handle detached HEAD, no-upstream, bare repos gracefully.
3. **Parallel fetch** — `ThreadPoolExecutor` over discovered repos.
   Bounded worker count (default ~16). Surface failures (no remote,
   auth fail) without aborting batch.
4. **Report** — `rich` table. Default: only repos needing attention
   (dirty OR behind OR stashed). `--all` flag shows every repo.
   `--json` for machine-readable.
5. **Optional actions** (later increment, gated):
   - `--pull-clean` pulls repos that are behind AND clean.
   - `--show-diff` prints `git status` per dirty repo.

CLI lib: stdlib `argparse` (keep deps light). Entry point `gitrep`.

Tests: pytest. Each module isolated. Integration test seeds a temp
tree of fake repos via `git init` + scripted commits.

## References

- `git rev-list --left-right --count` for ahead/behind.
- `rich.table.Table` for output.
- `concurrent.futures.ThreadPoolExecutor` — git fetch is I/O-bound.
