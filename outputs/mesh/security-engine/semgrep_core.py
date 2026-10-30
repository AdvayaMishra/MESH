"""Bounded target adapter for the pinned official OSS core; no Python Semgrep frontend."""

import json
import subprocess
from pathlib import Path

import yaml
from dependencies import prepare_semgrep_tree

VERSION = "1.182.1"
EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def target_manifest(root: Path) -> list:
    targets = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in EXTENSIONS:
            continue
        relative = path.relative_to(root).as_posix()
        targets.append(
            [
                "CodeTarget",
                {
                    "path": {"fpath": str(path), "ppath": "/" + relative},
                    "analyzer": EXTENSIONS[path.suffix.lower()],
                    "products": ["sast"],
                },
            ]
        )
        if len(targets) > 10000:
            raise ValueError("Semgrep target count exceeded")
    return ["Targets", targets]


def validate_report(data: dict, rule_ids: set[str]) -> dict:
    if (
        data.get("version") != VERSION
        or not isinstance(data.get("errors"), list)
        or data["errors"]
        or data.get("skipped_targets")
    ):
        raise ValueError("Incomplete Semgrep core assessment")
    if not isinstance(data.get("results"), list) or len(data["results"]) > 20000:
        raise ValueError("Invalid Semgrep core findings")
    for item in data["results"]:
        if item.get("check_id") not in rule_ids:
            raise ValueError("Unexpected Semgrep rule")
    return data


def scan(root: Path, target: Path, core: Path, rules: Path) -> dict:
    policy = yaml.safe_load(rules.read_text())
    rule_ids = {item["id"] for item in policy["rules"]}
    languages = {language for item in policy["rules"] for language in item["languages"]}
    if not rule_ids or not languages <= set(EXTENSIONS.values()):
        raise ValueError("Rules require an unsupported target language")
    prepare_semgrep_tree(root, target)
    manifest = target_manifest(target)
    if not manifest[1]:
        return {"version": VERSION, "results": [], "errors": []}
    targets_file = target.parent / "semgrep-targets.json"
    targets_file.write_text(json.dumps(manifest), encoding="utf-8")
    report_file = target.parent / "semgrep-core-report.json"
    with report_file.open("wb") as output:
        result = subprocess.run(
            [
                str(core),
                "-rules",
                str(rules),
                "-targets",
                str(targets_file),
                "-json",
                "-j",
                "1",
                "-use_parmap",
                "-strict",
                "-timeout",
                "5",
            ],
            stdout=output,
            stderr=subprocess.DEVNULL,
            timeout=150,
            check=False,
        )
    if result.returncode != 0 or report_file.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Semgrep core failed or exceeded output bound")
    # Pinned core emits progress dots before the JSON object.
    output = report_file.read_bytes()
    return validate_report(json.loads(output[output.index(b"{") :]), rule_ids)
