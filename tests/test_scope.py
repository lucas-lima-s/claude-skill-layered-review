from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import scope
from conftest import ROOT, commit_all, write_file


def test_glob_match_star_matches_within_segment() -> None:
    assert scope.glob_match("src/*.py", "src/service.py")
    assert not scope.glob_match("src/*.py", "src/orders/service.py")


def test_glob_match_double_star_matches_nested_paths() -> None:
    assert scope.glob_match("src/**/*.py", "src/orders/deep/service.py")
    assert scope.glob_match("src/**/*.py", "src/service.py")
    assert not scope.glob_match("src/**/*.py", "other/service.py")


def test_glob_match_double_star_matches_zero_segments() -> None:
    assert scope.glob_match("**/ui/**", "ui/button.tsx")
    assert scope.glob_match("**/ui/**", "app/ui/button.tsx")
    assert scope.glob_match("**/ui/**", "app/ui/nested/button.tsx")
    assert not scope.glob_match("**/ui/**", "app/components/button.tsx")


def test_to_posix_normalizes_backslashes() -> None:
    assert scope.to_posix("src\\orders\\service.py") == "src/orders/service.py"


def test_route_agents_fires_when_file_matches() -> None:
    config = {
        "agents": [
            {
                "name": "domain-reviewer",
                "file": "agents/domain-reviewer.md",
                "match": ["src/**/*.py"],
                "layer_priority": 3,
                "reason": "backend changed",
            }
        ]
    }
    fired, skipped = scope.route_agents(config, ["src/orders/service.py", "README.md"])
    assert len(fired) == 1
    assert fired[0]["name"] == "domain-reviewer"
    assert fired[0]["files"] == ["src/orders/service.py"]
    assert skipped == []


def test_route_agents_skips_when_no_match() -> None:
    config = {
        "agents": [
            {
                "name": "e2e-test-reviewer",
                "file": "agents/e2e-test-reviewer.md",
                "match": ["tests/e2e/**", "**/*.feature"],
                "layer_priority": 2,
                "reason": "e2e changed",
            }
        ]
    }
    fired, skipped = scope.route_agents(config, ["src/orders/service.py"])
    assert fired == []
    assert skipped == [{"name": "e2e-test-reviewer", "reason": "no matching files"}]


def test_collect_changed_files_unions_worktree_and_staged(git_repo: Path) -> None:
    write_file(git_repo, "a.py", "1\n")
    write_file(git_repo, "b.py", "1\n")
    commit_all(git_repo, "init")

    write_file(git_repo, "a.py", "2\n")
    write_file(git_repo, "b.py", "2\n")
    subprocess.run(["git", "add", "b.py"], cwd=git_repo, check=True, capture_output=True)

    changed, base_resolved = scope.collect_changed_files(
        git_repo, "main", include_staged=True, include_worktree=True
    )

    assert base_resolved is True
    assert set(changed) == {"a.py", "b.py"}


def test_unresolvable_base_falls_back_with_warning(git_repo: Path) -> None:
    write_file(git_repo, "a.py", "1\n")
    commit_all(git_repo, "init")
    write_file(git_repo, "a.py", "2\n")

    changed, base_resolved = scope.collect_changed_files(
        git_repo, "origin/does-not-exist", include_staged=True, include_worktree=True
    )

    assert base_resolved is False
    assert changed == ["a.py"]


def test_scope_cli_end_to_end_json(git_repo: Path) -> None:
    write_file(git_repo, "src/orders/service.py", "1\n")
    commit_all(git_repo, "init")
    write_file(git_repo, "src/orders/service.py", "2\n")

    config_path = ROOT / "review.example.toml"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "scope.py"),
            "--config",
            str(config_path),
            "--base",
            "main",
            "--repo",
            str(git_repo),
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "src/orders/service.py" in payload["changed_files"]
    assert payload["agents"] == []
    skipped = {a["name"]: a["reason"] for a in payload["skipped_agents"]}
    assert skipped["domain-reviewer"].startswith("placeholder agent")
    assert skipped["e2e-test-reviewer"] == "no matching files"


def test_scope_cli_fires_filled_project_agent_with_model(git_repo: Path) -> None:
    write_file(git_repo, "src/orders/service.py", "1\n")
    write_file(
        git_repo, "agents/orders.md", "---\nname: orders\n---\n\n## Scope\nsrc/orders only.\n"
    )
    write_file(
        git_repo,
        "review.toml",
        'base_ref = "main"\n\n[[agents]]\nname = "orders"\nfile = "agents/orders.md"\n'
        'match = ["src/orders/**"]\nlayer_priority = 3\nmodel = "sonnet"\n\n'
        '[[agents]]\nname = "ghost"\nfile = "agents/ghost.md"\nmatch = ["src/**"]\n',
    )
    commit_all(git_repo, "init")
    write_file(git_repo, "src/orders/service.py", "2\n")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "scope.py"),
            "--repo",
            str(git_repo),
            "--config",
            str(git_repo / "review.toml"),
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    fired = {a["name"]: a for a in payload["agents"]}
    assert fired["orders"]["model"] == "sonnet"
    assert fired["orders"]["file"].endswith("agents/orders.md")
    skipped = {a["name"]: a["reason"] for a in payload["skipped_agents"]}
    assert skipped["ghost"] == "agent file not found: agents/ghost.md"


def test_route_agents_skips_placeholder_agent(tmp_path: Path) -> None:
    write_file(tmp_path, "agents/todo.md", "## Scope\nTODO: fill me.\n")
    config = {"agents": [{"name": "todo", "file": "agents/todo.md", "match": ["**/*.py"]}]}
    fired, skipped = scope.route_agents(config, ["a.py"], [tmp_path])
    assert fired == []
    assert skipped[0]["reason"].startswith("placeholder agent")


def test_scope_cli_unresolvable_base_exits_zero_with_stderr_warning(git_repo: Path) -> None:
    write_file(git_repo, "a.py", "1\n")
    commit_all(git_repo, "init")
    write_file(git_repo, "a.py", "2\n")

    config_path = ROOT / "review.example.toml"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "scope.py"),
            "--config",
            str(config_path),
            "--base",
            "origin/does-not-exist",
            "--repo",
            str(git_repo),
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "warning" in result.stderr.lower()
    payload = json.loads(result.stdout)
    assert "a.py" in payload["changed_files"]
