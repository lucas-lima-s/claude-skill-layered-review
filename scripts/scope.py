from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import tomllib
from pathlib import Path


def to_posix(path: str) -> str:
    return path.replace("\\", "/")


def load_config(config_path: Path) -> dict:
    with config_path.open("rb") as fh:
        return tomllib.load(fh)


def run_git(args: list[str], repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )


def changed_from(result: subprocess.CompletedProcess) -> list[str]:
    if result.returncode != 0:
        return []
    return [to_posix(line) for line in result.stdout.splitlines() if line.strip()]


def resolve_base_diff(repo: Path, base: str) -> list[str] | None:
    result = run_git(["diff", "--name-only", f"{base}...HEAD"], repo)
    if result.returncode != 0:
        return None
    return changed_from(result)


def collect_changed_files(
    repo: Path, base: str, include_staged: bool, include_worktree: bool
) -> tuple[list[str], bool]:
    files: set[str] = set()
    base_resolved = True

    base_files = resolve_base_diff(repo, base)
    if base_files is None:
        base_resolved = False
    else:
        files.update(base_files)

    if include_worktree:
        files.update(changed_from(run_git(["diff", "--name-only"], repo)))

    if include_staged:
        files.update(changed_from(run_git(["diff", "--name-only", "--staged"], repo)))

    return sorted(files), base_resolved


def glob_match(pattern: str, path: str) -> bool:
    pattern_parts = pattern.split("/")
    path_parts = path.split("/")
    return _match_parts(pattern_parts, path_parts)


def _match_parts(pattern_parts: list[str], path_parts: list[str]) -> bool:
    if not pattern_parts:
        return not path_parts

    head, rest = pattern_parts[0], pattern_parts[1:]

    if head == "**":
        if _match_parts(rest, path_parts):
            return True
        if path_parts and _match_parts(pattern_parts, path_parts[1:]):
            return True
        return False

    if not path_parts:
        return False

    if not fnmatch.fnmatchcase(path_parts[0], head):
        return False

    return _match_parts(rest, path_parts[1:])


def route_agents(config: dict, changed_files: list[str]) -> tuple[list[dict], list[dict]]:
    fired: list[dict] = []
    skipped: list[dict] = []

    for agent in config.get("agents", []):
        patterns = agent.get("match", [])
        matched = sorted(f for f in changed_files if any(glob_match(p, f) for p in patterns))
        if matched:
            fired.append(
                {
                    "name": agent["name"],
                    "file": agent["file"],
                    "reason": agent.get("reason", ""),
                    "layer_priority": agent.get("layer_priority", 0),
                    "files": matched,
                }
            )
        else:
            skipped.append({"name": agent["name"], "reason": "no matching files"})

    return fired, skipped


def build_result(
    base: str,
    changed_files: list[str],
    agents: list[dict],
    skipped_agents: list[dict],
    generic_layer: dict,
) -> dict:
    return {
        "base": base,
        "changed_files": changed_files,
        "agents": agents,
        "generic_layer": {
            "enabled": generic_layer.get("enabled", True),
            "command": generic_layer.get("command", ""),
            "effort": generic_layer.get("effort", ""),
        },
        "skipped_agents": skipped_agents,
    }


def render_markdown(result: dict) -> str:
    lines = [f"# Review scope (base: {result['base']})", ""]
    lines.append(f"Changed files: {len(result['changed_files'])}")
    for f in result["changed_files"]:
        lines.append(f"- {f}")
    lines.append("")
    lines.append("## Agents to run")
    if result["agents"]:
        for agent in result["agents"]:
            lines.append(f"- {agent['name']}: {agent['reason']} ({len(agent['files'])} files)")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Agents skipped")
    if result["skipped_agents"]:
        for agent in result["skipped_agents"]:
            lines.append(f"- {agent['name']}: {agent['reason']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve local diff scope and route review agents."
    )
    parser.add_argument("--config", default="review.toml")
    parser.add_argument("--base", default=None)
    parser.add_argument("--repo", default=".")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--markdown", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo = Path(args.repo).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()

    config = load_config(config_path)
    base = args.base or config.get("base_ref", "origin/main")
    include_staged = config.get("include_staged", True)
    include_worktree = config.get("include_worktree", True)

    changed_files, base_resolved = collect_changed_files(
        repo, base, include_staged, include_worktree
    )

    if not base_resolved:
        print(
            f"warning: could not resolve base ref '{base}...HEAD', "
            "falling back to worktree + staged changes only",
            file=sys.stderr,
        )

    agents, skipped_agents = route_agents(config, changed_files)
    generic_layer = config.get("generic_layer", {})

    result = build_result(base, changed_files, agents, skipped_agents, generic_layer)

    if args.markdown:
        sys.stdout.write(render_markdown(result))
    else:
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
