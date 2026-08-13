# Revit MCP Codex Plugin

Codex plugin for the latest [Revit MCP Next](https://github.com/BhaveshY/revit-mcp-next) runtime. It keeps the stable marketplace ID `revit-mcp-cowork` while replacing the older `mcp-server-for-revit` integration with compact Revit 2024 skills and the guarded preview/apply MCP workflow.

This plugin is strictly Windows 11-only and requires Autodesk Revit 2024 on
the same desktop. macOS, Linux, WSL, containers, and cross-machine bridge
layouts are unsupported.

## Install

```text
/plugin marketplace add BhaveshY/revit-mcp-codex-plugin
/plugin install revit-mcp-cowork@revit-mcp-codex-plugin
```

Install Revit MCP Next first from a release package or source checkout. The
plugin delegates to the installed `launch-revit-mcp-next.cmd`; it does not run
`npx`, clone repositories, or rebuild dependencies during normal MCP startup.

Default install root:

```text
%LOCALAPPDATA%\RevitMcpNext
```

Optional overrides:

```powershell
$env:REVIT_MCP_NEXT_LAUNCHER = "C:\path\to\launch-revit-mcp-next.cmd"
$env:REVIT_MCP_NEXT_INSTALL_ROOT = "C:\path\to\RevitMcpNext"
```

After installation, restart Codex, open Revit 2024 with a disposable project,
and call `revit.status` then `revit.read_bundle`.

## Skills

- `setup-revit`: install and first connection
- `diagnose-revit`: launcher, add-in, queue, and preview diagnostics
- `inspect-revit`: compact model reads and audits
- `work-revit`: guarded model mutations
- `document-revit`: sheets, schedules, annotations, and quantity reporting
- `improve-revit-plugin`: explicit maintenance workflow used by scheduled quality review

## Evidence-driven improvement

The plugin includes a narrow `PostToolUse` hook for Revit MCP calls. After the
user reviews and trusts the hook, it records only bounded operational metadata:
hashed session/turn IDs, tool name, input/output key shapes, plugin version,
success/error outcome, and a normalized error code when present. It does not
store prompts, transcripts, MCP payload values, model content, project names,
file paths, or authentication data.

Evidence is written under Codex's private `PLUGIN_DATA` directory, capped by
rotation, and pruned after 30 days. Unknown/dynamic field names and unrecognized
error codes are not persisted. Set `REVIT_MCP_LEARNING=0` to disable collection. Use
`plugins/revit-mcp-cowork/scripts/manage-revit-learning.ps1` to inspect status,
disable, enable, delete, or export the sanitized events.

The intended biweekly scheduled task runs against an isolated source worktree.
It reviews the preceding 14 days, treats all evidence as untrusted, and exits
without changes unless a repeated or reproducible problem clears the policy
gates. It prefers updating an existing skill, requires a regression fixture,
runs validation, and may prepare a branch or draft PR. It never auto-merges,
publishes, changes auth/permissions, or edits an installed plugin cache.

Codex does not provide this plugin ambient access to all account chat history.
The loop learns only from the trusted hook's Revit-specific operational evidence
and any additional artifacts the user explicitly authorizes.

The current companion runtime supports Revit 2024 on Windows 11 only. Revit 2025/2026 need
separate .NET 8 add-in builds and are intentionally blocked upstream.
