from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import consolidate
import jsonschema
from conftest import ROOT

DEFAULT_ORDER = ["critical", "important", "suggestion"]


def make_finding(**overrides: object) -> dict:
    finding = {
        "severity": "important",
        "title": "Something is wrong here",
        "file": "src/a.py",
        "line": 10,
        "description": "",
        "rule_id": "",
    }
    finding.update(overrides)
    return finding


def test_same_file_and_line_merge() -> None:
    f1 = make_finding(rule_id="R1")
    f2 = make_finding(rule_id="R1")
    result = consolidate.consolidate(
        [("layer-a", 1, [f1]), ("layer-b", 2, [f2])], DEFAULT_ORDER, 2, 0.6, []
    )
    assert result["total_after_dedup"] == 1
    assert result["findings"][0]["merged_count"] == 2


def test_two_line_offset_merges_within_tolerance() -> None:
    f1 = make_finding(rule_id="R1", line=10)
    f2 = make_finding(rule_id="R1", line=12)
    result = consolidate.consolidate(
        [("layer-a", 1, [f1]), ("layer-b", 2, [f2])], DEFAULT_ORDER, 2, 0.6, []
    )
    assert result["total_after_dedup"] == 1


def test_four_line_offset_does_not_merge() -> None:
    f1 = make_finding(rule_id="R1", line=10)
    f2 = make_finding(rule_id="R1", line=14)
    result = consolidate.consolidate(
        [("layer-a", 1, [f1]), ("layer-b", 2, [f2])], DEFAULT_ORDER, 2, 0.6, []
    )
    assert result["total_after_dedup"] == 2


def test_equal_rule_id_merges_regardless_of_title() -> None:
    f1 = make_finding(rule_id="SAME", title="Completely different wording one")
    f2 = make_finding(rule_id="SAME", title="Nothing alike over here at all")
    result = consolidate.consolidate(
        [("layer-a", 1, [f1]), ("layer-b", 2, [f2])], DEFAULT_ORDER, 2, 0.6, []
    )
    assert result["total_after_dedup"] == 1


def test_jaccard_threshold_merges_and_below_does_not() -> None:
    high = make_finding(rule_id="", title="Discount code validated only on the client")
    high2 = make_finding(rule_id="", title="Discount code validated only on the client side")
    low = make_finding(rule_id="", title="Totally unrelated finding about logging")

    merged = consolidate.consolidate(
        [("layer-a", 1, [high]), ("layer-b", 2, [high2])], DEFAULT_ORDER, 2, 0.6, []
    )
    assert merged["total_after_dedup"] == 1

    not_merged = consolidate.consolidate(
        [("layer-a", 1, [high]), ("layer-b", 2, [low])], DEFAULT_ORDER, 2, 0.6, []
    )
    assert not_merged["total_after_dedup"] == 2


def test_higher_layer_priority_wins_survivor() -> None:
    low_priority = make_finding(rule_id="R1", title="From the weaker layer")
    high_priority = make_finding(rule_id="R1", title="From the stronger layer")
    result = consolidate.consolidate(
        [("weak", 1, [low_priority]), ("strong", 5, [high_priority])],
        DEFAULT_ORDER,
        2,
        0.6,
        [],
    )
    assert result["findings"][0]["title"] == "From the stronger layer"


def test_tie_break_severity_then_description_then_layer_name() -> None:
    critical = make_finding(rule_id="R1", severity="critical", title="Critical version")
    important = make_finding(rule_id="R1", severity="important", title="Important version")
    result = consolidate.consolidate(
        [("same-priority-b", 1, [important]), ("same-priority-a", 1, [critical])],
        DEFAULT_ORDER,
        2,
        0.6,
        [],
    )
    assert result["findings"][0]["severity"] == "critical"

    short_desc = make_finding(rule_id="R2", description="short")
    long_desc = make_finding(rule_id="R2", description="a much longer description text")
    result2 = consolidate.consolidate(
        [("layer-b", 1, [short_desc]), ("layer-a", 1, [long_desc])],
        DEFAULT_ORDER,
        2,
        0.6,
        [],
    )
    assert result2["findings"][0]["description"] == "a much longer description text"

    same_everything_1 = make_finding(rule_id="R3", description="same length")
    same_everything_2 = make_finding(rule_id="R3", description="same length")
    result3 = consolidate.consolidate(
        [("zeta", 1, [same_everything_1]), ("alpha", 1, [same_everything_2])],
        DEFAULT_ORDER,
        2,
        0.6,
        [],
    )
    assert result3["findings"][0]["sources"] == ["alpha", "zeta"]


def test_sources_and_merged_count_populated() -> None:
    f1 = make_finding(rule_id="R1")
    f2 = make_finding(rule_id="R1")
    standalone = make_finding(rule_id="", title="A totally standalone finding", line=999)
    result = consolidate.consolidate(
        [("layer-a", 1, [f1, standalone]), ("layer-b", 2, [f2])], DEFAULT_ORDER, 2, 0.6, []
    )
    merged = next(f for f in result["findings"] if f["merged_count"] == 2)
    assert merged["sources"] == ["layer-a", "layer-b"]
    single = next(f for f in result["findings"] if f["merged_count"] == 1)
    assert single["sources"] == ["layer-a"]


def test_severity_ordering_follows_configured_order() -> None:
    critical = make_finding(severity="critical", title="c", line=1)
    important = make_finding(severity="important", title="i", line=2)
    suggestion = make_finding(severity="suggestion", title="s", line=3)
    custom_order = ["suggestion", "important", "critical"]
    result = consolidate.consolidate(
        [("layer", 1, [critical, important, suggestion])], custom_order, 2, 0.6, []
    )
    assert [f["severity"] for f in result["findings"]] == custom_order


def test_zero_finding_layer_renders_as_clean() -> None:
    result = consolidate.consolidate([("e2e-test-reviewer", 2, [])], DEFAULT_ORDER, 2, 0.6, [])
    markdown = consolidate.render_markdown(result, DEFAULT_ORDER)
    assert "0 - clean" in markdown


def test_exit_code_returns_1_only_when_critical_survives(tmp_path: Path) -> None:
    critical_file = tmp_path / "critical.json"
    critical_file.write_text(
        json.dumps(
            {
                "layer": "layer",
                "layer_priority": 1,
                "findings": [make_finding(severity="critical", title="boom")],
            }
        ),
        encoding="utf-8",
    )
    clean_file = tmp_path / "clean.json"
    clean_file.write_text(
        json.dumps(
            {
                "layer": "layer",
                "layer_priority": 1,
                "findings": [make_finding(severity="suggestion", title="minor")],
            }
        ),
        encoding="utf-8",
    )

    critical_run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "consolidate.py"),
            str(critical_file),
            "--format",
            "json",
            "--exit-code",
        ],
        capture_output=True,
        text=True,
    )
    assert critical_run.returncode == 1

    clean_run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "consolidate.py"),
            str(clean_file),
            "--format",
            "json",
            "--exit-code",
        ],
        capture_output=True,
        text=True,
    )
    assert clean_run.returncode == 0


def test_examples_match_schema() -> None:
    schema = json.loads((ROOT / "schema" / "finding.schema.json").read_text(encoding="utf-8"))
    for example_file in (ROOT / "examples").glob("findings-*.json"):
        data = json.loads(example_file.read_text(encoding="utf-8"))
        for finding in data["findings"]:
            jsonschema.validate(instance=finding, schema=schema)
