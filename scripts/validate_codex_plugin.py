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
    "name", "version", "description", "skills", "apps", "mcpServers",
    "hooks", "interface", "author", "homepage", "repository", "license", "keywords",
}
ALLOWED_INTERFACE_KEYS = {
    "displayName", "shortDescription", "longDescription", "developerName", "category",
    "capabilities", "websiteURL", "privacyPolicyURL", "termsOfServiceURL", "brandColor",
    "composerIcon", "logo", "logoDark", "screenshots", "defaultPrompt",
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


def parse_mcp_dependencies(agent_text: str) -> list[tuple[str, str]]:
    dependencies: list[tuple[str, str]] = []
    lines = agent_text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s*-\s+type:\s*['\"]?mcp['\"]?\s*$", line):
            continue
        item_indent = len(line) - len(line.lstrip())
        block: list[str] = []
        for candidate in lines[index + 1:]:
            if candidate.strip():
                indent = len(candidate) - len(candidate.lstrip())
                if indent <= item_indent:
                    break
            block.append(candidate)
        block_text = "\n".join(block)
        value_match = re.search(r"^\s*value:\s*['\"]?([^'\"\s]+)", block_text, re.M)
        transport_match = re.search(r"^\s*transport:\s*['\"]?([^'\"\s]+)", block_text, re.M)
        dependencies.append((value_match.group(1) if value_match else "", transport_match.group(1) if transport_match else ""))
    return dependencies


def validate_skill_files(skills_dir: Path, mcp_server_names: set[str], errors: list[str]) -> set[str]:
    bound_servers: set[str] = set()
    if not skills_dir.is_dir():
        errors.append(f"skills directory does not exist: {skills_dir}")
        return bound_servers
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        errors.append(f"no skills found under {skills_dir}")
        return bound_servers
    descriptions: dict[str, Path] = {}
    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        if len(text.splitlines()) > 200:
            errors.append(f"{path} exceeds the 200-line skill budget")
        if not text.startswith("---\n"):
            errors.append(f"{path} is missing YAML frontmatter")
            continue
        end = text.find("\n---", 4)
        if end == -1:
            errors.append(f"{path} has unterminated YAML frontmatter")
            continue
        frontmatter = text[4:end]
        name_match = re.search(r"^name:\s*([^\s]+)\s*$", frontmatter, re.M)
        if not name_match:
            errors.append(f"{path} frontmatter is missing name")
        elif name_match.group(1) != path.parent.name:
            errors.append(f"{path} name must match skill folder {path.parent.name!r}")
        description_match = re.search(r"^description:\s*(\S.*)$", frontmatter, re.M)
        if not description_match:
            errors.append(f"{path} frontmatter is missing description")
        else:
            normalized = re.sub(r"[^a-z0-9]+", " ", description_match.group(1).lower()).strip()
            if normalized in descriptions:
                errors.append(f"{path} duplicates the description in {descriptions[normalized]}")
            descriptions[normalized] = path
        if "[TODO:" in text:
            errors.append(f"{path} contains [TODO: placeholder")
        agent_path = path.parent / "agents" / "openai.yaml"
        try:
            agent_text = agent_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"{path.parent} is missing agents/openai.yaml")
            continue
        for key in ["display_name", "short_description", "default_prompt"]:
            if not re.search(rf"^\s*{key}:\s*\S+", agent_text, re.M):
                errors.append(f"{agent_path} is missing interface.{key}")
        if name_match and f"${name_match.group(1)}" not in agent_text:
            errors.append(f"{agent_path} default_prompt must mention ${name_match.group(1)}")
        implicit_match = re.search(r"^\s*allow_implicit_invocation:\s*(true|false)\s*$", agent_text, re.M | re.I)
        expected_implicit = path.parent.name != "improve-revit-plugin"
        if not implicit_match:
            errors.append(f"{agent_path} must set policy.allow_implicit_invocation")
        elif (implicit_match.group(1).lower() == "true") != expected_implicit:
            expected = str(expected_implicit).lower()
            errors.append(f"{agent_path} must set policy.allow_implicit_invocation: {expected}")
        dependencies = parse_mcp_dependencies(agent_text)
        if re.search(r"^dependencies:\s*$", agent_text, re.M) and not dependencies:
            errors.append(f"{agent_path} dependencies must include an MCP tool entry")
        for server_name, transport in dependencies:
            if not server_name:
                errors.append(f"{agent_path} MCP dependency is missing value")
                continue
            bound_servers.add(server_name)
            if server_name not in mcp_server_names:
                errors.append(f"{agent_path} binds undeclared MCP server {server_name!r}")
            if transport != "stdio":
                errors.append(f"{agent_path} MCP dependency {server_name!r} must use stdio transport")
    return bound_servers


def resolve_relative_token(plugin_root: Path, token: str) -> Path | None:
    if not isinstance(token, str):
        return None
    cleaned = token.strip('"').strip("'")
    if cleaned.startswith("./") or cleaned.startswith(".\\"):
        return plugin_root / cleaned[2:].replace("\\", "/")
    return None


def validate_mcp_servers(mcp_path: Path, plugin_root: Path, errors: list[str]) -> set[str]:
    mcp = load_json(mcp_path, errors)
    if not isinstance(mcp, dict) or not isinstance(mcp.get("mcpServers"), dict) or not mcp["mcpServers"]:
        errors.append(f"{mcp_path} must contain a non-empty mcpServers object")
        return set()
    server_names = set(mcp["mcpServers"])
    for server_name, server_config in mcp["mcpServers"].items():
        label = f"{mcp_path} mcpServers.{server_name}"
        if not isinstance(server_config, dict):
            errors.append(f"{label} must be an object")
            continue
        if server_config.get("type") != "stdio":
            errors.append(f"{label}.type must be 'stdio'")
        if not nonempty_string(server_config.get("command")):
            errors.append(f"{label}.command must be a non-empty string")
        if server_config.get("cwd") != ".":
            errors.append(f"{label}.cwd must be '.'")
        args = server_config.get("args")
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            errors.append(f"{label}.args must be a string array")
            args = []
        if not isinstance(server_config.get("env"), dict):
            errors.append(f"{label}.env must be an object")
        timeout = server_config.get("timeout")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1000 <= timeout <= 300000:
            errors.append(f"{label}.timeout must be an integer from 1000 to 300000 milliseconds")
        for arg in args:
            script_path = resolve_relative_token(plugin_root, arg)
            if script_path and script_path.suffix.lower() in {".cmd", ".ps1", ".js"} and not script_path.is_file():
                errors.append(f"{label} references missing script: {arg}")
    return server_names


def validate_hooks_file(hooks_path: Path, plugin_root: Path, errors: list[str]) -> None:
    hooks_config = load_json(hooks_path, errors)
    if not isinstance(hooks_config, dict):
        errors.append(f"{hooks_path} must contain an object")
        return
    hooks = hooks_config.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        errors.append(f"{hooks_path} must contain a non-empty hooks object")
        return
    for event_name, event_entries in hooks.items():
        if not isinstance(event_entries, list) or not event_entries:
            errors.append(f"{hooks_path} hooks.{event_name} must be a non-empty array")
            continue
        for event_index, event_entry in enumerate(event_entries):
            commands = event_entry.get("hooks") if isinstance(event_entry, dict) else None
            if not isinstance(commands, list) or not commands:
                errors.append(f"{hooks_path} hooks.{event_name}[{event_index}].hooks must be a non-empty array")
                continue
            for hook_index, hook in enumerate(commands):
                if not isinstance(hook, dict):
                    errors.append(f"{hooks_path} hooks.{event_name}[{event_index}].hooks[{hook_index}] must be an object")
                    continue
                if hook.get("type") != "command":
                    errors.append(f"{hooks_path} hooks.{event_name}[{event_index}].hooks[{hook_index}].type must be 'command'")
                    continue
                command = hook.get("command")
                if not nonempty_string(command):
                    errors.append(f"{hooks_path} hooks.{event_name}[{event_index}].hooks[{hook_index}].command is required")
                    continue
                for command_value in [command, hook.get("commandWindows")]:
                    if command_value is None:
                        continue
                    if not nonempty_string(command_value):
                        errors.append(f"{hooks_path} hook command override must be a non-empty string")
                        continue
                    for match in re.finditer(r"\$\{PLUGIN_ROOT\}[\\/]([^\"']+\.(?:ps1|py|js|cmd))", command_value):
                        script_path = plugin_root / match.group(1).replace("\\", "/")
                        if not script_path.is_file():
                            errors.append(f"{hooks_path} references missing hook script: {match.group(1)}")


def validate_learning_files(plugin_root: Path, errors: list[str]) -> None:
    learning = plugin_root / "learning"
    policy = load_json(learning / "policy.json", errors)
    catalog = load_json(learning / "capabilities.json", errors)
    ledger = load_json(learning / "ledger.json", errors)
    if not all(isinstance(value, dict) and value.get("schema_version") == 1 for value in [policy, catalog, ledger]):
        errors.append("learning policy, capabilities, and ledger must use schema_version 1")
        return
    if policy.get("auto_merge") is not False or policy.get("auto_publish") is not False:
        errors.append("learning policy must keep auto_merge and auto_publish false")
    if not policy.get("allow_no_change"):
        errors.append("learning policy must allow a no-change cycle")
    if policy.get("retention_days") != 30:
        errors.append("learning evidence retention_days must be 30")
    allowed_paths = policy.get("allowed_automatic_paths", [])
    if "learning/ledger.json" not in allowed_paths:
        errors.append("learning ledger must be an explicitly allowed automatic metadata path")
    skill_names = {path.parent.name for path in (plugin_root / "skills").glob("*/SKILL.md")}
    catalog_names = {item.get("name") for item in catalog.get("skills", []) if isinstance(item, dict)}
    expected_catalog = skill_names - {"improve-revit-plugin"}
    if catalog_names != expected_catalog:
        errors.append("learning capability catalog must list every user-facing skill exactly once")
    if not isinstance(ledger.get("incidents"), list):
        errors.append("learning ledger incidents must be an array")
    else:
        allowed_statuses = {"handled", "dismissed"}
        seen_fingerprints: set[str] = set()
        for index, incident in enumerate(ledger["incidents"]):
            if not isinstance(incident, dict):
                errors.append(f"learning ledger incident {index} must be an object")
                continue
            allowed_incident_keys = {"fingerprint", "status", "plugin_version", "decided_at_utc", "decision"}
            unknown = set(incident) - allowed_incident_keys
            if unknown:
                errors.append(f"learning ledger incident {index} has unknown keys: {', '.join(sorted(unknown))}")
            fingerprint = incident.get("fingerprint")
            if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{20}", fingerprint):
                errors.append(f"learning ledger incident {index} has an invalid fingerprint")
            elif fingerprint in seen_fingerprints:
                errors.append(f"learning ledger repeats fingerprint {fingerprint}")
            else:
                seen_fingerprints.add(fingerprint)
            if incident.get("status") not in allowed_statuses:
                errors.append(f"learning ledger incident {index} has an invalid status")
            for key in ["plugin_version", "decided_at_utc", "decision"]:
                if not nonempty_string(incident.get(key)) or len(incident[key]) > 200:
                    errors.append(f"learning ledger incident {index} has an invalid {key}")
    eval_paths = sorted((learning / "evals").glob("*.json"))
    if not eval_paths:
        errors.append("learning/evals must contain at least one sanitized regression fixture")
    for path in eval_paths:
        fixture = load_json(path, errors)
        if not isinstance(fixture, dict) or fixture.get("schema_version") != 1 or not isinstance(fixture.get("cases"), list):
            errors.append(f"{path} must contain schema_version 1 and a cases array")
    forbidden_keys = {"prompt", "transcript", "tool_input", "tool_response", "cwd", "file_path", "email", "token", "auth"}
    for path in [learning / "capabilities.json", learning / "ledger.json"] + eval_paths:
        value = load_json(path, errors)
        serialized_keys: set[str] = set()
        def collect_keys(item: Any) -> None:
            if isinstance(item, dict):
                serialized_keys.update(str(key).lower() for key in item)
                for child in item.values():
                    collect_keys(child)
            elif isinstance(item, list):
                for child in item:
                    collect_keys(child)
        collect_keys(value)
        found = sorted(serialized_keys & forbidden_keys)
        if found:
            errors.append(f"{path} contains forbidden evidence keys: {', '.join(found)}")


def validate_safety_invariants(plugin_root: Path, errors: list[str]) -> None:
    work = (plugin_root / "skills" / "work-revit" / "SKILL.md").read_text(encoding="utf-8")
    safety = (plugin_root / "references" / "write-safety.md").read_text(encoding="utf-8")
    combined = work + "\n" + safety
    required = ["preview_change_set", "apply_change_set", "confirm=true", "generation", "Verify"]
    for token in required:
        if token.lower() not in combined.lower():
            errors.append(f"Revit write safety invariant is missing: {token}")


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
    mcp_server_names: set[str] = set()
    if manifest.get("mcpServers"):
        mcp_path = plugin_root / str(manifest["mcpServers"]).replace("./", "")
        mcp_server_names = validate_mcp_servers(mcp_path, plugin_root, errors)
    if manifest.get("skills"):
        skill_path = manifest["skills"]
        if skill_path != "./skills/":
            errors.append("plugin.json skills should be './skills/'")
        bound_servers = validate_skill_files(plugin_root / skill_path.replace("./", ""), mcp_server_names, errors)
        for missing_server in sorted(mcp_server_names - bound_servers):
            errors.append(f"MCP server {missing_server!r} is not bound by any skill agents/openai.yaml")
    hooks_path = plugin_root / "hooks" / "hooks.json"
    if hooks_path.exists():
        validate_hooks_file(hooks_path, plugin_root, errors)
    validate_learning_files(plugin_root, errors)
    validate_safety_invariants(plugin_root, errors)
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
