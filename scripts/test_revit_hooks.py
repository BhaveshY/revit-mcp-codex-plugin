#!/usr/bin/env python3
"""Smoke tests for bundled Revit hook scripts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugins" / "revit-mcp-cowork" / "hooks"


def run_hook(name: str, payload: dict) -> dict:
    proc = subprocess.run(
        ["node", str(HOOKS / name)],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return json.loads(proc.stdout or "{}")


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> int:
    denied = run_hook("pre-tool.js", {"tool_name": "mcp__revit__say_hello", "tool_input": {}})
    assert_equal(denied["hookSpecificOutput"]["permissionDecision"], "deny", "say_hello is denied")
    if "send_code_to_revit" not in denied["hookSpecificOutput"]["permissionDecisionReason"]:
        raise AssertionError("say_hello denial must point users at send_code_to_revit")

    capped = run_hook("pre-tool.js", {"tool_name": "mcp__revit__get_current_view_elements", "tool_input": {}})
    assert_equal(capped["hookSpecificOutput"]["permissionDecision"], "deny", "missing safe limit is denied")
    if '"limit": 100000' not in capped["hookSpecificOutput"]["permissionDecisionReason"]:
        raise AssertionError("limit denial must include exact retry parameter")

    allowed = run_hook("pre-tool.js", {"tool_name": "mcp__revit__get_current_view_elements", "tool_input": {"limit": 100000}})
    assert_equal(allowed["hookSpecificOutput"]["permissionDecision"], "allow", "safe limit is allowed")

    warned = run_hook(
        "post-tool.js",
        {"tool_name": "mcp__revit__get_current_view_elements", "tool_response": {"Elements": [{}] * 100}},
    )
    if "TRUNCATED" not in warned["hookSpecificOutput"]["additionalContext"]:
        raise AssertionError("post-tool hook must warn about exact silent cap lengths")

    failed = run_hook("post-tool.js", {"tool_name": "mcp__revit__send_code_to_revit", "tool_response": {"Success": False, "Message": "失败"}})
    if "Success=false" not in failed["hookSpecificOutput"]["additionalContext"]:
        raise AssertionError("post-tool hook must surface failed Revit responses")

    started = run_hook("session-start.js", {})
    if "Revit MCP Tool Safety" not in started["hookSpecificOutput"]["additionalContext"]:
        raise AssertionError("session-start hook must inject safety context")

    print("Revit hook smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
