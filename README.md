# gitrep

Multi-repo status and mass-fetch manager. Scans a directory tree for git
repositories, fetches them in parallel, and reports which ones need
attention (dirty, ahead/behind origin, stashed work, or errors).

## Install

Requires the mamba env `gitrep` (python 3.12). `environment.yml` creates it
and installs the package in editable mode:

```
mamba env create -f environment.yml
mamba activate gitrep
```

Or, in an existing environment: `pip install -e .[dev]`.

This puts the `gitrep` console script on PATH.

## Usage

Default invocation scans `/code`, fetches all repos in parallel, and
prints a table of repos needing attention:

```
gitrep
```

Skip the network fetch (read-only inspection only):

```
gitrep --no-fetch
```

Show every repo, not just attention-needing ones:

```
gitrep --all
```

Machine-readable output:

```
gitrep --json
```

Scan a different root:

```
gitrep --root /some/other/dir
```

## Key flags

| flag | effect |
|------|--------|
| `--root PATH` | Root to scan (default `/code`) |
| `--all` | Show all repos, not only attention-needing |
| `--json` | Emit JSON instead of a table |
| `--no-fetch` | Skip the parallel `git fetch` step |
| `--workers N` | Fetch worker count (default 16) |
| `--fetch-timeout S` | Per-repo fetch timeout in seconds (default 30) |
| `--inspect-timeout S` | Timeout in seconds for each git command run while inspecting a repo (default 10) |
| `--include-submodules` | Include submodule `.git`-file repos |
| `--show-diff` | Print `git status -s` for each dirty repo |
| `--upstream-status` | Add ahead/behind columns vs `origin/HEAD` and vs `origin/<current-branch>` |
| `--remote-status` | Add a column with the number of configured remotes |
| `--pull-clean` | Prompt to `git pull --ff-only` repos that are clean, behind their upstream, not detached, and have exactly one remote |

## Safety

The default invocation performs `git fetch` (the one explicit network
side effect). All mutating actions (`--pull-clean`) require an explicit
flag and an interactive confirmation prompt. No push, rebase, merge, or
commit operations are performed under any flag.

## Tests and linting

```
pytest
ruff check . && ruff format --check .
mypy
```
