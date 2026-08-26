---
name: <agent-name>
description: <one line: what this reviewer is expert in and when it should fire>
tools: Read, Grep, Glob
---

# <Agent name>

## Scope
TODO: which files and which kinds of change this agent owns.

## Invariants to protect
TODO: 3 to 7 rules that must never be violated in this domain. Each with a
one-line rationale and an observable symptom when broken.

## What to ignore
TODO: known-acceptable patterns, so the agent does not re-report accepted debt.

## Output contract
Return a JSON object: {"layer": "<agent-name>", "layer_priority": <n>,
"findings": [{"severity": "critical|important|suggestion", "title": ...,
"file": ..., "line": ..., "description": ..., "fix": ..., "rule_id": ...}]}
Report nothing you cannot point at with file and line. If the diff is clean
for your scope, return an empty findings array - never invent findings.
