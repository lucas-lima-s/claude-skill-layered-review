# Setup

This skill has no external dependencies beyond a git repository and
Python's standard library at runtime; the dev tooling below is only needed
to run the test suite and linters, not to use the skill itself.

## Requirements

- Python >= 3.11 (for `tomllib`, used by both scripts to read `review.toml`).
- [`uv`](https://docs.astral.sh/uv/) for the dev workflow (`uv sync`,
  `uv run`), or a plain virtualenv with `requirements-dev.txt` installed.
- `git`, on `PATH`, for `scripts/scope.py` to shell out to.

## Per-project configuration

Every project that uses this skill needs its own `review.toml` in its
repository root - it is intentionally not tracked here (see `.gitignore`).
Start from the tracked example:

```
cp review.example.toml review.toml
```

Then edit:

- `base_ref` - the branch this project's pull requests target (for example
  `origin/main` or `origin/develop`).
- `[[agents]]` - replace the illustrative `match` globs with this project's
  real directory layout, and either keep, edit, or remove the four
  placeholder agents in `agents/`.
- `[dedup]` and `[severity]` - tune to taste; the defaults shipped in
  `review.example.toml` are reasonable starting points.

No environment variables, API tokens, or credentials are required by
anything in this repository.

## Installing dev dependencies

With `uv` (recommended - this is what CI uses):

```
uv sync --dev
```

Without `uv`:

```
python -m venv .venv
.venv/Scripts/activate   # or: source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Running the checks locally

```
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

The CI workflow (`.github/workflows/ci.yml`) runs the same three commands
across Python 3.11/3.12/3.13 on both Ubuntu and Windows, plus a check that
`scripts/consolidate.py` reproduces `examples/expected-report.md` byte for
byte.
