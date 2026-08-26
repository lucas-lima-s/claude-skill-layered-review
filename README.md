# claude-skill-layered-review

A [Claude Code](https://claude.com/claude-code) skill template for **layered
local code review**: a generic review pass, plus pluggable domain-specialist
subagents chosen by what the diff touches, consolidated into one
deduplicated, severity-grouped report.

```
                    ┌─────────────────┐
   local diff  ───▶ │   scope.py      │  routes changed files to agents
                    └────────┬────────┘
                             │
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
      ┌───────────────┐ ┌──────────┐ ┌─────────────────┐
      │ generic layer  │ │ domain-  │ │ ux-flow-reviewer │  ... (concurrent)
      │  (/code-review)│ │ reviewer │ │  coherence-guard.│
      └───────┬────────┘ └────┬─────┘ └────────┬─────────┘
              │                │                │
              └────────────────┼────────────────┘
                                ▼
                       ┌─────────────────┐
                       │ consolidate.py  │  dedup + severity grouping
                       └────────┬────────┘
                                ▼
                     one Markdown / JSON report
```

The generic layer has no domain knowledge; it catches correctness bugs and
simplification opportunities anywhere in the diff. Domain agents are
narrow specialists that fire only when the diff touches paths they own, so a
UI-only change never wastes a backend reviewer's attention (and the report
says so explicitly instead of staying silent about it).

This repository ships the orchestration prompt (`SKILL.md`), four
fill-in-the-blanks agent templates, and two small, fully-tested Python
tools that make the mechanical parts of the pattern deterministic:

- `scripts/scope.py` - resolves what changed (base branch diff, worktree,
  staged) and routes it to the configured agents by glob match.
- `scripts/consolidate.py` - merges every layer's findings into one
  deduplicated, severity-ordered report.

## Installation

Copy this repository's contents into a project (or point Claude Code's
skill search path at it). Then, in that project:

```
cp review.example.toml review.toml
```

Edit `review.toml`: set `base_ref` to the branch you diff against, and adjust
or replace the `[[agents]]` entries so their `match` globs point at this
project's real directories. `review.toml` is gitignored on purpose - it is
per-project configuration, not something this template should own.

## Usage

From Claude Code, trigger the skill by name or by one of its natural
phrasings ("layered review", "review my local diff", "run the review
agents"). It will:

1. Resolve scope with `scripts/scope.py`.
2. Run the generic layer (`/code-review` by default).
3. Fan out to every domain agent whose paths were touched, concurrently.
4. Consolidate everything with `scripts/consolidate.py`.
5. Print one report, grouped by severity, with clean layers stated
   explicitly and merged findings crediting every layer that found them.

You can also run the two scripts directly, outside of Claude Code:

```
python scripts/scope.py --config review.toml --base origin/main --json

python scripts/consolidate.py --config review.toml \
    generic.json domain-reviewer.json e2e-test-reviewer.json \
    --format markdown
```

## Configuration

See `review.example.toml` for a fully-annotated example. The relevant
sections:

- `base_ref`, `include_staged`, `include_worktree` - which changes count as
  "the diff".
- `[generic_layer]` - the command, effort, and priority of the
  non-specialist pass.
- `[[agents]]` - one entry per domain agent: its name, its instructions
  file under `agents/`, the glob patterns that decide whether it fires, its
  `layer_priority` (higher wins when two layers report the same defect),
  and a human-readable `reason` shown when it is skipped.
- `[dedup]` - `line_tolerance` (how many lines apart two findings can be and
  still be considered the same spot) and `title_similarity` (the Jaccard
  threshold for merging by title when there is no shared `rule_id`).
- `[severity]` - the order findings are grouped and sorted in.

## Writing your own domain agent

The four shipped agents (`domain-reviewer`, `ux-flow-reviewer`,
`coherence-guardian`, `e2e-test-reviewer`) are placeholders: each has the
required frontmatter and output contract filled in, worked example
invariants, and `TODO:` markers where a real project's specifics belong. See
[`docs/writing-a-domain-agent.md`](docs/writing-a-domain-agent.md) for the
full walkthrough of adding a fifth, and
[`docs/dedup-algorithm.md`](docs/dedup-algorithm.md) for exactly how findings
get merged.

## Sample consolidated report

Running `scripts/consolidate.py` against the fixtures in `examples/`
produces a report that starts like this (see
[`examples/expected-report.md`](examples/expected-report.md) for the full,
golden output):

```
# Layered review

layers: generic (12 findings), domain-reviewer (5 findings), e2e-test-reviewer (0 - clean)
not run: ux-flow-reviewer (no matching files), coherence-guardian (no matching files)
after dedup: 14 findings (3 merged)

## Critical

### src/orders/service.py:89 - Order total recomputed from cart after the discount is already subtracted

finalize_order() calls compute_subtotal(cart) again after apply_discount() has already mutated the cart total, silently discarding the discount on the persisted order.

**Fix:** Compute the subtotal once, apply the discount to that value, and persist the result without recomputing from the cart.

**Sources:** domain-reviewer, generic
```

Note how the surviving finding is the domain reviewer's more specific
version (it has the higher `layer_priority`), while `sources` still credits
both layers that reported it.

## Development

```
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full contribution workflow.

## License

[MIT](LICENSE)
