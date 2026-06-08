#!/usr/bin/env python3
"""Self-contained sanity validator for repo-local Codex plugin packages."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
ALLOWED_PLUGIN_KEYS = {
    "id", "name", "version", "description", "skills", "apps", "mcpServers",
    "interface", "author", "homepage", "repository", "license", "keywords",
}
ALLOWED_INTERFACE_KEYS = {
    "displayName", "shortDescription", "longDescription", "developerName", "category",
    "capabilities", "websiteURL", "privacyPolicyURL", "termsOfServiceURL", "brandColor",
    "composerIcon", "logo", "screenshots", "defaultPrompt", "default_prompt",
}


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing JSON file: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: {exc}")
    return None


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def reject_todos(value: Any, label: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if "[TODO:" in value:
            errors.append(f"{label} contains [TODO: placeholder")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            reject_todos(item, f"{label}[{i}]", errors)
    elif isinstance(value, dict):
        for key, item in value.items():
            reject_todos(item, f"{label}.{key}", errors)


def validate_skill_files(skills_dir: Path, errors: list[str]) -> None:
    if not skills_dir.is_dir():
        errors.append(f"skills directory does not exist: {skills_dir}")
        return
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        errors.append(f"no skills found under {skills_dir}")
        return
    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            errors.append(f"{path} is missing YAML frontmatter")
            continue
        end = text.find("\n---", 4)
        if end == -1:
            errors.append(f"{path} has unterminated YAML frontmatter")
            continue
        frontmatter = text[4:end]
        if not re.search(r"^name:\s*\S+", frontmatter, re.M):
            errors.append(f"{path} frontmatter is missing name")
        if not re.search(r"^description:\s*\S+", frontmatter, re.M):
            errors.append(f"{path} frontmatter is missing description")
        if "[TODO:" in text:
            errors.append(f"{path} contains [TODO: placeholder")


def validate(repo_root: Path, plugin_rel: str) -> list[str]:
    errors: list[str] = []
    plugin_root = (repo_root / plugin_rel).resolve()
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    marketplace_path = repo_root / ".agents" / "plugins" / "marketplace.json"
    manifest = load_json(manifest_path, errors)
    marketplace = load_json(marketplace_path, errors)
    if not isinstance(manifest, dict):
        errors.append("plugin.json must contain an object")
        return errors
    reject_todos(manifest, "plugin.json", errors)
    unknown = sorted(set(manifest) - ALLOWED_PLUGIN_KEYS)
    if unknown:
        errors.append(f"plugin.json contains unsupported keys: {', '.join(unknown)}")
    for key in ["name", "version", "description"]:
        if not nonempty_string(manifest.get(key)):
            errors.append(f"plugin.json field {key!r} must be a non-empty string")
    if nonempty_string(manifest.get("version")) and not SEMVER_RE.fullmatch(manifest["version"]):
        errors.append("plugin.json version must be strict semver")
    author = manifest.get("author")
    if not isinstance(author, dict) or not nonempty_string(author.get("name")):
        errors.append("plugin.json author.name is required")
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append("plugin.json interface object is required")
    else:
        unknown_interface = sorted(set(interface) - ALLOWED_INTERFACE_KEYS)
        if unknown_interface:
            errors.append(f"plugin.json interface contains unsupported keys: {', '.join(unknown_interface)}")
        for key in ["displayName", "shortDescription", "longDescription", "developerName", "category"]:
            if not nonempty_string(interface.get(key)):
                errors.append(f"plugin.json interface.{key} must be a non-empty string")
        caps = interface.get("capabilities")
        if not isinstance(caps, list) or not all(nonempty_string(v) for v in caps):
            errors.append("plugin.json interface.capabilities must be a non-empty string array")
        if "defaultPrompt" not in interface and "default_prompt" not in interface:
            errors.append("plugin.json interface.defaultPrompt is required")
    if manifest.get("skills"):
        skill_path = manifest["skills"]
        if skill_path != "./skills/":
            errors.append("plugin.json skills should be './skills/'")
        validate_skill_files(plugin_root / skill_path.replace("./", ""), errors)
    if manifest.get("mcpServers"):
        mcp_path = plugin_root / str(manifest["mcpServers"]).replace("./", "")
        mcp = load_json(mcp_path, errors)
        if not isinstance(mcp, dict) or not isinstance(mcp.get("mcpServers"), dict) or not mcp["mcpServers"]:
            errors.append(f"{mcp_path} must contain a non-empty mcpServers object")
    if not isinstance(marketplace, dict):
        errors.append("marketplace.json must contain an object")
        return errors
    if not nonempty_string(marketplace.get("name")):
        errors.append("marketplace.json name is required")
    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or not entries:
        errors.append("marketplace.json plugins must be a non-empty array")
    else:
        matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("name") == manifest.get("name")]
        if len(matches) != 1:
            errors.append(f"marketplace.json must contain exactly one entry for plugin {manifest.get('name')!r}")
        else:
            entry = matches[0]
            expected_path = "./" + plugin_rel.replace("\\", "/")
            source = entry.get("source")
            if not isinstance(source, dict) or source.get("source") != "local" or source.get("path") != expected_path:
                errors.append(f"marketplace entry source must be local path {expected_path}")
            policy = entry.get("policy")
            if not isinstance(policy, dict) or policy.get("installation") != "AVAILABLE" or policy.get("authentication") != "ON_INSTALL":
                errors.append("marketplace entry policy must set installation=AVAILABLE and authentication=ON_INSTALL")
            if not nonempty_string(entry.get("category")):
                errors.append("marketplace entry category is required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin_path", help="plugin path relative to repo root, e.g. plugins/name")
    args = parser.parse_args()
    repo_root = Path.cwd().resolve()
    errors = validate(repo_root, args.plugin_path)
    if errors:
        print("Codex plugin validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Codex plugin validation passed: {args.plugin_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
