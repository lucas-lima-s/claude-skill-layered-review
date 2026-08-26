# Contributing

## Development setup

```
uv sync --dev
```

See [`SETUP.md`](SETUP.md) for requirements and the non-`uv` alternative.

## Before opening a pull request

```
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

All three must pass. `pytest` should report at least the tests currently in
`tests/` passing with none failing; if you add behavior, add a test for it
in `tests/test_scope.py` or `tests/test_consolidate.py` alongside it.

If you change the dedup algorithm, the glob-matching semantics, or the
Markdown report layout, also update:

- `docs/dedup-algorithm.md` (if the dedup rules changed),
- the fixtures in `examples/` and `examples/expected-report.md` /
  `examples/expected-report.json` (regenerate them by running
  `scripts/consolidate.py` against the fixtures and saving the output - do
  not hand-edit the golden files), and
- `CHANGELOG.md` under `## [Unreleased]`.

## Code style

- Stdlib only in `scripts/scope.py` and `scripts/consolidate.py` - no new
  runtime dependencies. Dev-only tools (`pytest`, `ruff`, `jsonschema`) are
  fine in `tests/`.
- `from __future__ import annotations` at the top of every script, PEP
  585/604 type hints (`list[str]`, `int | None`), no inline comments.
- No new agent template should skip the `## Output contract` section - the
  JSON shape is what makes every agent's findings mergeable by
  `consolidate.py`.

## Adding or changing an agent template

See [`docs/writing-a-domain-agent.md`](docs/writing-a-domain-agent.md).

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) style
(`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`), in English.
