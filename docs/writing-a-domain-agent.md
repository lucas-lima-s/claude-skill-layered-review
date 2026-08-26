# Writing a domain agent

A domain agent is a subagent definition file that reviews the part of a diff
it is expert in, and returns findings in one fixed JSON shape so the
consolidation step (`scripts/consolidate.py`) can merge them with everything
else. This guide walks through adding a fifth agent to the four shipped in
`agents/`.

## 1. Decide what it owns

Pick a scope narrow enough that the agent can be genuinely expert in it. Good
scopes correspond to a real architectural boundary: "database migrations",
"public API handlers", "the payments module". A scope that is really "all
backend code" duplicates `domain-reviewer` instead of adding a new
perspective.

## 2. Copy the template

Start from `agents/_TEMPLATE.md`:

```
cp agents/_TEMPLATE.md agents/my-new-reviewer.md
```

Fill in the frontmatter (`name`, `description`, `tools`) and every `TODO:`
marker:

- **Scope** - the exact directories, file extensions, or module boundaries
  this agent should read. Be specific; this text guides the agent, it is not
  matched against the diff (`review.toml` glob patterns do that).
- **Invariants to protect** - 3 to 7 rules, each with a one-line rationale
  (why the rule exists) and an observable symptom (what a violation looks
  like in production or in a bug report). Two or three well-chosen
  invariants beat seven vague ones.
- **What to ignore** - the project's known-acceptable exceptions to those
  invariants, so the agent does not re-report debt the team has already
  decided to accept.
- **Output contract** - leave this section as-is except for the agent name;
  it is what makes every agent's output mergeable by `consolidate.py`.

## 3. Wire it into `review.toml`

Add an `[[agents]]` entry:

```toml
[[agents]]
name = "my-new-reviewer"
file = "agents/my-new-reviewer.md"
match = ["path/glob/**"]
layer_priority = 2
reason = "why this agent's scope was touched"
```

- `match` uses the same `**`-aware glob semantics as every other agent (see
  `scripts/scope.py`): a segment of `**` matches zero or more path segments,
  any other segment matches exactly one path segment with `fnmatch`-style
  wildcards.
- `layer_priority` decides which layer wins when two layers report the same
  defect (see `docs/dedup-algorithm.md`). A more specific, narrowly-scoped
  agent should usually outrank the generic layer.
- `reason` is shown in the report whenever the agent is skipped, so keep it
  short and specific ("a new migration was added", not "files changed").

## 4. Verify it fires and stays quiet when it should

Run the scope resolver against a branch that touches the agent's globs and
confirm it appears in `agents`, and against one that does not to confirm it
lands in `skipped_agents`:

```
python scripts/scope.py --config review.toml --base main --json
```

Then feed it a findings file (matching `schema/finding.schema.json`) through
`scripts/consolidate.py` and check that a clean run reports `0 - clean`
rather than being silently omitted - the anti-noise rule this template
enforces mechanically.
