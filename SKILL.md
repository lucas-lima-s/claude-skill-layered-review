---
name: layered-review
description: Review the current local diff in layers - a generic code-review pass plus the domain reviewer subagents whose paths the diff touches - then consolidate everything into one deduplicated, severity-grouped report. Never commits; reports only. Use before opening a pull request or when the user asks for a thorough local review. Triggers on "layered review", "review my local diff", "run the review agents", "revisao local", "revisa meu diff local", "/layered-review".
---

# Layered review

Review the current local diff in layers: a generic pass, then every domain
reviewer subagent whose configured paths the diff actually touches, then one
consolidated report that deduplicates overlapping findings and groups
everything by severity.

## Preconditions

This skill needs two things:

1. A git repository - the diff comes from `git`, so there must be a repo to
   diff against.
2. A `review.toml` in the repository root - copy `review.example.toml` and
   adjust the `base_ref`, the `[[agents]]` entries, and the dedup thresholds
   for this project.

If `review.toml` has no `[[agents]]` entries (or the file is missing and no
agents can be resolved), the generic layer still runs alone, and the final
report says explicitly that no domain agents were configured - it never
pretends a layer ran when it did not.

## Step 0: resolve scope

Run the scope resolver to find out what changed and which agents apply:

```
python scripts/scope.py --config review.toml --json
```

This unions the diff against `base_ref` with the worktree and staged changes
(per `include_worktree` / `include_staged`), matches every changed file
against each configured agent's `match` globs, and returns which agents fire
(with the exact files that triggered them) and which are skipped (with a
reason). If `base_ref` cannot be resolved - a common case on a fresh branch
with no upstream yet - it degrades to worktree + staged changes only and
says so on stderr; it still exits `0`.

## Step 1: generic layer

Run the generic review pass named in `[generic_layer]` (`/code-review` by
default) at the configured `effort`, scoped to the changed files from Step
0. This is the layer that has no domain-specific knowledge - it catches
correctness bugs and simplification opportunities anywhere in the diff.

## Step 2: domain layer

Launch every agent that `scope.py` listed under `agents` as an isolated
subagent, **in a single message so they run concurrently** - there is no
dependency between them, and running them serially only adds latency. Pass
each agent the exact file list `scope.py` assigned it, plus the agent's own
Markdown file from `agents/` as its instructions. Every agent must return
its findings in the JSON shape defined in its own `## Output contract`
section (see `schema/finding.schema.json`).

## Step 3: consolidation

Write each layer's output (the generic layer's findings reshaped into the
same `{"layer", "layer_priority", "findings"}` shape, plus one file per
domain agent) to disk, then consolidate:

```
python scripts/consolidate.py --config review.toml generic.json domain-reviewer.json ... --format markdown
```

This deduplicates findings that describe the same defect across layers
(same file, nearby line, and either a matching `rule_id` or a similar
title - see `docs/dedup-algorithm.md`), keeps the more specific layer's
version when two layers report the same thing, and groups the survivors by
severity per `[severity].order`. A layer that returned zero findings is
still printed, as `0 - clean` - silence about a layer that ran is treated as
a bug in the report, not a feature.

## Step 4: publishing findings

This skill does not know how to post to any specific forge, tracker, or
chat tool - that is deliberately out of scope. `consolidate.py --format
json` emits a report that validates against `schema/finding.schema.json`
plus a `sources` and `merged_count` on every finding; adapting that JSON
into a pull request comment, an issue, or a Slack message is left to the
adopter. The required mapping is: `severity` to whatever priority levels
the target tool uses, `file` + `line` to its inline-comment anchor (when it
has one), and `title` + `description` + `fix` to the comment body.

## Step 5: the `/simplify` gate

If an automated simplification pass (`/simplify` or equivalent) touches any
file this review already covered, re-run the domain layer - not just the
generic layer - on those files before considering the diff done.
Simplification can remove a compatibility path, a guard clause, or a cache
that exists for a domain reason the generic layer cannot see.

## Hard rules

- Never commit. This skill reports; it does not fix, stage, or push.
- Never invent a finding. Every finding must point at a real file and line;
  an agent with nothing to report returns an empty findings array.
- Always state a clean layer explicitly. `0 - clean` beats silence.
- When two layers report the same defect, prefer the more specific layer's
  version - that is what `layer_priority` and the dedup survivor rule exist
  to guarantee.
