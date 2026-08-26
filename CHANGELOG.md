# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-25

### Added

- `scripts/scope.py`: resolves the changed-file scope of a local diff (base ref,
  staged, worktree) and routes it to the agents configured in `review.toml` by
  glob match.
- `scripts/consolidate.py`: merges findings from multiple review layers into one
  deduplicated, severity-grouped report (Markdown or JSON).
- Four placeholder domain-reviewer agent templates plus the shared template they
  follow, and a guide for writing a fifth.
- `SKILL.md` describing the layered-review workflow: generic pass, domain
  subagents fanned out concurrently, consolidation, publishing, and the
  `/simplify` re-review gate.
- Golden-report fixtures and a full pytest suite covering routing and
  consolidation.
