#!/usr/bin/env python3
"""Cluster sanitized Revit MCP events without reading prompts or payload values."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ALLOWED_EVENT_KEYS = {
    "schema_version", "timestamp_utc", "session_hash", "turn_hash", "tool_name",
    "plugin_version", "outcome", "error_code", "input_shape", "response_shape",
}
FORBIDDEN_EVENT_KEYS = {
    "prompt", "transcript", "transcript_path", "cwd", "tool_input", "tool_response",
    "content", "project_name", "file_path", "user", "email", "auth", "token",
}
HASH_RE = re.compile(r"^[a-f0-9]{16}$")
TOOL_RE = re.compile(r"^(?:mcp__revit-mcp-next__[a-zA-Z0-9_-]+|revit\.[a-zA-Z0-9_.-]+)$")
CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\[\]-]{0,79}$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validate_event(event: dict[str, Any], location: str, cutoff: datetime, now: datetime) -> bool:
    unknown = set(event) - ALLOWED_EVENT_KEYS
    forbidden = set(event) & FORBIDDEN_EVENT_KEYS
    if unknown or forbidden:
        names = ", ".join(sorted(unknown | forbidden))
        raise ValueError(f"{location}: unsafe or unknown event keys: {names}")
    if event.get("schema_version") != 1:
        raise ValueError(f"{location}: unsupported event schema")
    try:
        timestamp = parse_timestamp(str(event["timestamp_utc"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{location}: invalid timestamp") from exc
    if timestamp > now + timedelta(minutes=5):
        raise ValueError(f"{location}: future-dated event")
    for name in ("session_hash", "turn_hash"):
        value = event.get(name)
        if value is not None and (not isinstance(value, str) or not HASH_RE.fullmatch(value)):
            raise ValueError(f"{location}: invalid {name}")
    if not isinstance(event.get("tool_name"), str) or not TOOL_RE.fullmatch(event["tool_name"]):
        raise ValueError(f"{location}: invalid tool_name")
    if event.get("outcome") not in {"success", "error"}:
        raise ValueError(f"{location}: invalid outcome")
    code = event.get("error_code")
    if code is not None and (not isinstance(code, str) or not CODE_RE.fullmatch(code)):
        raise ValueError(f"{location}: invalid error_code")
    if event.get("outcome") == "success" and code is not None:
        raise ValueError(f"{location}: successful event cannot contain error_code")
    version = event.get("plugin_version")
    if version is not None and (not isinstance(version, str) or len(version) > 64):
        raise ValueError(f"{location}: invalid plugin_version")
    for name in ("input_shape", "response_shape"):
        shape = event.get(name)
        if not isinstance(shape, list) or len(shape) > 96 or any(
            not isinstance(item, str) or not SHAPE_RE.fullmatch(item) for item in shape
        ):
            raise ValueError(f"{location}: invalid {name}")
    return timestamp >= cutoff


def iter_events(paths: Iterable[Path], cutoff: datetime, max_bytes: int, now: datetime | None = None) -> Iterable[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    consumed = 0
    for path in paths:
        if not path.is_file():
            continue
        size = path.stat().st_size
        if consumed + size > max_bytes:
            raise ValueError(f"evidence byte budget exceeded before reading {path}")
        consumed += size
        for number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not raw_line.strip():
                continue
            event = json.loads(raw_line)
            if not isinstance(event, dict):
                raise ValueError(f"{path}:{number}: event must be an object")
            if validate_event(event, f"{path}:{number}", cutoff, now):
                yield event


def fingerprint(event: dict[str, Any]) -> str:
    stable = {
        "tool_name": event.get("tool_name"),
        "outcome": event.get("outcome"),
        "error_code": event.get("error_code"),
        "input_shape": sorted(event.get("input_shape") or []),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:20]


def owner_for(code: str | None, catalog: dict[str, Any]) -> str | None:
    if not code:
        return None
    owners = [item["name"] for item in catalog.get("skills", []) if code in item.get("failure_codes", [])]
    return owners[0] if len(owners) == 1 else None


def analyze(
    events: Iterable[dict[str, Any]], policy: dict[str, Any], catalog: dict[str, Any], ledger: dict[str, Any] | None = None
) -> dict[str, Any]:
    ledger_by_fingerprint = {
        item["fingerprint"]: item for item in (ledger or {}).get("incidents", [])
        if isinstance(item, dict) and isinstance(item.get("fingerprint"), str)
    }
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("outcome") != "success":
            groups[fingerprint(event)].append(event)

    candidates = []
    for incident_id, grouped in sorted(groups.items()):
        sessions = sorted({str(event.get("session_hash")) for event in grouped if event.get("session_hash")})
        occurrences = len({
            (event.get("session_hash"), event.get("turn_hash"), event.get("tool_name"), event.get("error_code"))
            for event in grouped
        })
        eligible = (
            occurrences >= int(policy["minimum_occurrences"])
            and len(sessions) >= int(policy["minimum_independent_sessions"])
        )
        sample = grouped[0]
        owner = owner_for(sample.get("error_code"), catalog)
        prior = ledger_by_fingerprint.get(incident_id)
        versions = {event.get("plugin_version") for event in grouped}
        suppressed = bool(
            prior
            and prior.get("status") in {"handled", "dismissed"}
            and versions == {prior.get("plugin_version")}
        )
        candidates.append({
            "fingerprint": incident_id,
            "tool_name": sample.get("tool_name"),
            "error_code": sample.get("error_code"),
            "occurrences": occurrences,
            "independent_sessions": len(sessions),
            "first_seen": min(event["timestamp_utc"] for event in grouped),
            "last_seen": max(event["timestamp_utc"] for event in grouped),
            "existing_owner": owner,
            "eligible_for_review": eligible and not suppressed,
            "ledger_status": prior.get("status") if prior else None,
            "reopened_after_version_change": bool(prior and not suppressed),
            "recommended_action": "suppressed-by-ledger" if suppressed else (
                "update-existing-skill" if eligible and owner else "classify-root-cause"
            ),
        })

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "eligible_count": sum(1 for item in candidates if item["eligible_for_review"]),
        "candidates": candidates,
    }


def default_event_paths() -> list[Path]:
    import os

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    locator = Path(local_app_data) / "RevitMcpNext" / "CodexLearning" / "plugin-data-location.json"
    if not locator.is_file():
        return []
    plugin_data = Path(load_json(locator)["plugin_data"])
    root = plugin_data / "learning-evidence"
    return [root / "events.1.jsonl", root / "events.jsonl"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", action="append", type=Path, help="sanitized JSONL event file")
    parser.add_argument("--plugin-root", type=Path, default=Path("plugins/revit-mcp-cowork"))
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    policy = load_json(args.plugin_root / "learning" / "policy.json")
    catalog = load_json(args.plugin_root / "learning" / "capabilities.json")
    ledger = load_json(args.plugin_root / "learning" / "ledger.json")
    lookback = args.lookback_days or int(policy["lookback_days"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback)
    paths = args.events or default_event_paths()
    report = analyze(iter_events(paths, cutoff, int(policy["max_evidence_bytes"])), policy, catalog, ledger)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
