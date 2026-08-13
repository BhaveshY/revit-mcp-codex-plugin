#!/usr/bin/env python3
"""Fail closed when an unattended learned patch exceeds its allowed surface."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_REL = Path("plugins/revit-mcp-cowork")
PRIVATE_NAME_RE = re.compile(r"(?:^|/)(?:events(?:\.1)?\.jsonl|learning-report\.json|transcript[^/]*)$", re.I)
SENSITIVE_VALUE_RE = re.compile(r"(?:[A-Z]:\\|/Users/|/home/|-----BEGIN |\bsk-[A-Za-z0-9_-]{10,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})")
FORBIDDEN_KEYS = {"prompt", "transcript", "tool_input", "tool_response", "cwd", "file_path", "email", "auth", "token"}


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def allowed(path: str, policy: dict) -> bool:
    rel = Path(path).as_posix()
    plugin_prefix = PLUGIN_REL.as_posix() + "/"
    if not rel.startswith(plugin_prefix):
        return False
    local = rel[len(plugin_prefix):]
    return any(local == item.rstrip("/") or local.startswith(item.rstrip("/") + "/") for item in policy["allowed_automatic_paths"])


def inspect_json(value: object, location: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                errors.append(f"{location}: forbidden key {key!r}")
            inspect_json(child, location, errors)
    elif isinstance(value, list):
        for child in value:
            inspect_json(child, location, errors)
    elif isinstance(value, str):
        if len(value) > 500 or SENSITIVE_VALUE_RE.search(value):
            errors.append(f"{location}: suspicious or oversized string value")


def validate(base: str) -> list[str]:
    policy = json.loads((ROOT / PLUGIN_REL / "learning/policy.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    branch = git("branch", "--show-current").strip()
    if branch in {"main", "master"} or not branch.startswith("codex/"):
        errors.append(f"learned patches require a codex/* branch, not {branch or '<detached>'}")
    statuses: dict[str, str] = {}
    for line in git("diff", "--name-status", base).splitlines():
        parts = line.split("\t")
        if parts:
            statuses[parts[-1].replace("\\", "/")] = parts[0]
    for path in git("ls-files", "--others", "--exclude-standard").splitlines():
        statuses[path.replace("\\", "/")] = "A"

    for path in sorted(statuses):
        if not allowed(path, policy):
            errors.append(f"path is outside the learned-change allowlist: {path}")
        if PRIVATE_NAME_RE.search(path):
            errors.append(f"private evidence/report file is forbidden: {path}")
        disk_path = ROOT / path
        if disk_path.is_symlink():
            errors.append(f"symlink is forbidden: {path}")
        if path.endswith("references/write-safety.md"):
            errors.append("the write-safety contract cannot be changed unattended")
        if disk_path.is_file() and disk_path.suffix.lower() == ".json" and (
            "/learning/evals/" in f"/{path}" or path.endswith("/learning/ledger.json")
        ):
            try:
                inspect_json(json.loads(disk_path.read_text(encoding="utf-8-sig")), path, errors)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"invalid JSON in {path}: {exc}")

    numstat = git("diff", "--numstat", base).splitlines()
    additions = deletions = 0
    for line in numstat:
        added, deleted, path = line.split("\t", 2)
        if added == "-" or deleted == "-":
            errors.append(f"binary change is forbidden: {path}")
            continue
        additions += int(added)
        deletions += int(deleted)
    for path, status in statuses.items():
        disk_path = ROOT / path
        if status == "A" and disk_path.is_file() and path not in {line.split("\t", 2)[-1] for line in numstat}:
            try:
                additions += len(disk_path.read_text(encoding="utf-8").splitlines())
            except UnicodeDecodeError:
                errors.append(f"binary/unreadable new file is forbidden: {path}")
    if additions - deletions > int(policy["max_net_new_lines"]):
        errors.append(f"net-new-line budget exceeded: +{additions - deletions}")

    changed_existing = 0
    new_skill_names: set[str] = set()
    for path, status in statuses.items():
        local = Path(path).as_posix().removeprefix(PLUGIN_REL.as_posix() + "/")
        if local.startswith("skills/") and status == "A":
            parts = local.split("/")
            if len(parts) > 1:
                result = subprocess.run(
                    ["git", "cat-file", "-e", f"{base}:{PLUGIN_REL.as_posix()}/skills/{parts[1]}/SKILL.md"],
                    cwd=ROOT, capture_output=True,
                )
                if result.returncode:
                    new_skill_names.add(parts[1])
        if status != "A" and not local.startswith("learning/evals/") and local != "learning/ledger.json":
            changed_existing += 1
    if len(new_skill_names) > int(policy["max_new_skills_per_cycle"]):
        errors.append(f"new-skill budget exceeded: {len(new_skill_names)}")
    if changed_existing > int(policy["max_existing_file_edits_per_cycle"]):
        errors.append(f"existing-file edit budget exceeded: {changed_existing}")
    behavior_paths = [
        path for path in statuses
        if f"/{path.replace(chr(92), '/')}".find(f"/{PLUGIN_REL.as_posix()}/skills/") >= 0
        or f"/{path.replace(chr(92), '/')}".find(f"/{PLUGIN_REL.as_posix()}/references/") >= 0
    ]
    if behavior_paths:
        eval_prefix = f"{PLUGIN_REL.as_posix()}/learning/evals/"
        ledger_path = f"{PLUGIN_REL.as_posix()}/learning/ledger.json"
        if not any(path.startswith(eval_prefix) for path in statuses):
            errors.append("skill/reference changes require a changed synthetic regression eval")
        if ledger_path not in statuses:
            errors.append("skill/reference changes require a ledger update")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    try:
        errors = validate(args.base)
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        print(f"Learning patch validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Learning patch validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Learning patch validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
