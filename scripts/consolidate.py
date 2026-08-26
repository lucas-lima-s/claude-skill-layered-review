from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

DEFAULT_SEVERITY_ORDER = ["critical", "important", "suggestion"]
DEFAULT_LINE_TOLERANCE = 2
DEFAULT_TITLE_SIMILARITY = 0.6

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "is",
    "are",
    "was",
    "were",
    "be",
    "with",
    "that",
    "this",
    "it",
    "as",
    "by",
    "at",
}

TOKEN_RE = re.compile(r"[^a-z0-9]+")


def normalize_file(path: str) -> str:
    return path.replace("\\", "/")


def tokenize(title: str) -> set[str]:
    words = TOKEN_RE.split(title.lower())
    return {w for w in words if w and w not in STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def load_config(config_path: Path | None) -> dict:
    if config_path is None or not config_path.exists():
        return {}
    with config_path.open("rb") as fh:
        return tomllib.load(fh)


def load_findings_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def flatten_findings(layer_files: list[tuple[str, int, list[dict]]]) -> list[dict]:
    flat = []
    for layer_name, layer_priority, findings in layer_files:
        for finding in findings:
            record = dict(finding)
            record["file"] = normalize_file(record["file"])
            record["_layer"] = layer_name
            record["_layer_priority"] = layer_priority
            record["_tokens"] = tokenize(record["title"])
            flat.append(record)
    return flat


def is_candidate(f1: dict, f2: dict, line_tolerance: int) -> bool:
    return f1["file"] == f2["file"] and abs(f1["line"] - f2["line"]) <= line_tolerance


def should_merge(f1: dict, f2: dict, title_similarity: float) -> bool:
    rule1, rule2 = f1.get("rule_id"), f2.get("rule_id")
    if rule1 and rule2 and rule1 == rule2:
        return True
    return jaccard(f1["_tokens"], f2["_tokens"]) >= title_similarity


def group_findings(
    flat: list[dict], line_tolerance: int, title_similarity: float
) -> list[list[dict]]:
    dsu = DisjointSet(len(flat))
    for i in range(len(flat)):
        for j in range(i + 1, len(flat)):
            if is_candidate(flat[i], flat[j], line_tolerance) and should_merge(
                flat[i], flat[j], title_similarity
            ):
                dsu.union(i, j)

    groups: dict[int, list[dict]] = {}
    for idx, record in enumerate(flat):
        root = dsu.find(idx)
        groups.setdefault(root, []).append(record)
    return list(groups.values())


def severity_rank(severity: str, order: list[str]) -> int:
    try:
        return order.index(severity)
    except ValueError:
        return len(order)


def pick_survivor(group: list[dict], severity_order: list[str]) -> dict:
    def sort_key(record: dict) -> tuple:
        return (
            -record["_layer_priority"],
            severity_rank(record["severity"], severity_order),
            -len(record.get("description", "") or ""),
            record["_layer"],
        )

    return sorted(group, key=sort_key)[0]


FINDING_FIELDS = [
    "severity",
    "title",
    "file",
    "line",
    "description",
    "fix",
    "rule_id",
    "confidence",
    "snippet",
]


def build_merged_finding(group: list[dict], severity_order: list[str]) -> dict:
    survivor = pick_survivor(group, severity_order)
    output = {k: survivor[k] for k in FINDING_FIELDS if k in survivor}
    output["sources"] = sorted({record["_layer"] for record in group})
    output["merged_count"] = len(group)
    return output


def consolidate(
    layer_files: list[tuple[str, int, list[dict]]],
    severity_order: list[str],
    line_tolerance: int,
    title_similarity: float,
    not_run: list[dict],
) -> dict:
    flat = flatten_findings(layer_files)
    total_before = len(flat)

    groups = group_findings(flat, line_tolerance, title_similarity)
    merged = [build_merged_finding(group, severity_order) for group in groups]

    merged.sort(
        key=lambda f: (
            severity_rank(f["severity"], severity_order),
            f["file"],
            f["line"],
            f["title"],
        )
    )

    total_after = len(merged)

    return {
        "layers": [{"name": name, "count": len(findings)} for name, _, findings in layer_files],
        "not_run": not_run,
        "total_before_dedup": total_before,
        "total_after_dedup": total_after,
        "merged_away": total_before - total_after,
        "findings": merged,
    }


def render_markdown(result: dict, severity_order: list[str]) -> str:
    lines = ["# Layered review", ""]

    layer_parts = []
    for layer in result["layers"]:
        if layer["count"] == 0:
            layer_parts.append(f"{layer['name']} (0 - clean)")
        else:
            layer_parts.append(f"{layer['name']} ({layer['count']} findings)")
    lines.append(f"layers: {', '.join(layer_parts)}")

    if result["not_run"]:
        not_run_parts = [f"{a['name']} ({a['reason']})" for a in result["not_run"]]
        lines.append(f"not run: {', '.join(not_run_parts)}")

    lines.append(
        f"after dedup: {result['total_after_dedup']} findings ({result['merged_away']} merged)"
    )

    by_severity: dict[str, list[dict]] = {s: [] for s in severity_order}
    for finding in result["findings"]:
        by_severity.setdefault(finding["severity"], []).append(finding)

    for severity in severity_order:
        findings = by_severity.get(severity, [])
        if not findings:
            continue
        lines.append("")
        lines.append(f"## {severity.capitalize()}")
        for finding in findings:
            lines.append("")
            lines.append(f"### {finding['file']}:{finding['line']} - {finding['title']}")
            description = finding.get("description")
            if description:
                lines.append("")
                lines.append(description)
            fix = finding.get("fix")
            if fix:
                lines.append("")
                lines.append(f"**Fix:** {fix}")
            lines.append("")
            lines.append(f"**Sources:** {', '.join(finding['sources'])}")

    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consolidate layered review findings.")
    parser.add_argument("--config", default="review.toml")
    parser.add_argument("findings_files", nargs="+")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--out", default=None)
    parser.add_argument("--exit-code", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    config_path = Path(args.config)
    config = load_config(config_path if config_path.exists() else None)

    severity_order = config.get("severity", {}).get("order", DEFAULT_SEVERITY_ORDER)
    dedup_config = config.get("dedup", {})
    line_tolerance = dedup_config.get("line_tolerance", DEFAULT_LINE_TOLERANCE)
    title_similarity = dedup_config.get("title_similarity", DEFAULT_TITLE_SIMILARITY)

    layer_files: list[tuple[str, int, list[dict]]] = []
    for file_path in args.findings_files:
        data = load_findings_file(Path(file_path))
        layer_files.append((data["layer"], data.get("layer_priority", 0), data["findings"]))

    seen_layers = {name for name, _, _ in layer_files}
    not_run = [
        {"name": agent["name"], "reason": "no matching files"}
        for agent in config.get("agents", [])
        if agent["name"] not in seen_layers
    ]

    result = consolidate(layer_files, severity_order, line_tolerance, title_similarity, not_run)

    if args.format == "json":
        output = json.dumps(result, indent=2) + "\n"
    else:
        output = render_markdown(result, severity_order)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)

    if args.exit_code:
        has_critical = any(f["severity"] == "critical" for f in result["findings"])
        return 1 if has_critical else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
