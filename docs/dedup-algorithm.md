# Dedup algorithm

`scripts/consolidate.py` merges findings that describe the same underlying
defect from different review layers into one record. This is the exact
algorithm, so it can be tested and tuned without reading the code.

## 1. Normalize

Every finding's `file` is normalized to a POSIX-style relative path
(backslashes become forward slashes) before any comparison happens.

## 2. Candidate pairs

Two findings are **candidates** for merging when both hold:

- the same normalized `file`, and
- `abs(line_a - line_b) <= line_tolerance` (from `[dedup].line_tolerance` in
  `review.toml`, default `2`).

Findings in different files, or more than `line_tolerance` lines apart in the
same file, are never merged, regardless of how similar their titles are.

## 3. Merge test

A candidate pair actually merges when **either**:

- both findings carry a non-empty `rule_id` and the two are equal, **or**
- the Jaccard similarity of their title token sets is
  `>= title_similarity` (from `[dedup].title_similarity`, default `0.6`).

Title tokenization: lowercase the title, split on any run of non-alphanumeric
characters, drop empty tokens, then drop a small fixed stopword list (`a`,
`an`, `the`, `and`, `or`, `of`, `to`, `in`, `on`, `for`, `is`, `are`, `was`,
`were`, `be`, `with`, `that`, `this`, `it`, `as`, `by`, `at`). Jaccard
similarity is `|intersection| / |union|` of the two token sets.

Merging is transitive: if A merges with B and B merges with C, all three land
in one group even if A and C alone would not have merged.

## 4. Picking the survivor

Every finding in a merged group is a candidate to be the surviving record.
The survivor is chosen by, in order:

1. **Highest `layer_priority`** - the layer_priority value attached to the
   findings file the finding came from (`{"layer": ..., "layer_priority": N,
   "findings": [...]}`). A more specific layer (say, a domain agent at
   priority 3) beats the generic layer (priority 1) when both report the
   same defect.
2. **More severe `severity`** - ranked by the order in `[severity].order`
   (default `critical`, `important`, `suggestion`; index 0 is most severe).
3. **Longer `description`** - the record with more explanatory text wins,
   on the theory that it is the more useful one to show the reader.
4. **Lexicographically smaller layer name** - a final deterministic
   tiebreaker so the result never depends on input file order.

## 5. Output

The survivor's fields are kept as-is. Two fields are added:

- `sources`: the sorted, de-duplicated list of every layer name that
  contributed a finding to the group (even the layers that lost the
  survivor vote).
- `merged_count`: how many original findings were folded into this one.

A finding that had no candidates keeps its own fields, `sources` set to its
own layer, and `merged_count` of `1`.

## 6. Ordering

The final list is sorted by `severity` (per `[severity].order`), then by
`file`, then by `line`, then by `title` - fully deterministic given the same
inputs and config.

## 7. Reporting a clean layer

A layer that contributed zero findings is never omitted from the report: it
is listed explicitly as `0 - clean`. An agent that was never run at all
(because `scripts/scope.py` found no matching files) is listed separately
under `not run`, with its skip reason. Silence about a layer is treated as a
bug in the report, not a feature.
