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

Select the plugin starter **Set up the weekly Revit learning automation on this
PC** once. Codex verifies the existing Revit MCP runtime, creates a dedicated
pinned maintenance task with its own writable source checkout, and creates or
repairs the Monday 11:00 AM automation. The task uses `gpt-5.6-sol` at medium
reasoning effort; no path or project ID is copied from the publisher's PC.

Codex does not currently expose an install-time scheduled-task hook, so plugin
installation itself cannot silently activate the automation. The setup starter
is the one supported onboarding action. The plugin hook separately requires
Codex's security trust prompt. A teammate also needs GitHub write access to open
draft PRs against this repository; without it, reviews remain local and report
the permission gap.

## Skills

- `setup-revit`: install, first connection, and weekly learning setup
- `diagnose-revit`: launcher, add-in, queue, and preview diagnostics
- `inspect-revit`: compact model reads and audits
- `work-revit`: guarded model mutations
- `document-revit`: sheets, schedules, annotations, and quantity reporting
- `improve-revit-plugin`: explicit maintenance workflow used by scheduled quality review

## Evidence-driven improvement

After the one-time setup starter, every Monday at 11:00 AM local time, a Codex
desktop automation reviews recent
tasks through the app's task-history tools using `gpt-5.6-sol` at medium
reasoning effort. It opens likely Revit tasks, reads their turns and tool results,
and looks for corrections, inaccurate answers, failed attempts, and repeated
friction. Raw chats remain in Codex; the plugin does not build a second
transcript database or commit chat text.

The first review covers the preceding 14 days. Each successful run stores one
ignored local timestamp; the next run reviews tasks updated after that point,
with a 24-hour overlap to catch boundary edits. Failed or incomplete runs do not
advance the timestamp.

The app returns at most 50 recent tasks. If all 50 are newer than the review
cutoff, the run is marked incomplete and the timestamp is not advanced. This
prevents an unusually busy week from silently skipping older tasks.

The plugin also includes a narrow `PostToolUse` hook for Revit MCP calls. After
the user reviews and trusts the hook, it records bounded operational metadata
to corroborate task-history findings: hashed session/turn IDs, tool name,
allowlisted input/output shapes, plugin version, outcome, and normalized error.

Evidence is written under Codex's private `PLUGIN_DATA` directory, capped by
rotation, and pruned after 30 days. Unknown/dynamic field names and unrecognized
error codes are not persisted. Set `REVIT_MCP_LEARNING=0` to disable collection. Use
`plugins/revit-mcp-cowork/scripts/manage-revit-learning.ps1` to inspect status,
disable, enable, delete, or export the sanitized events.

The scheduled task exits without changes unless repeated or reproducible
evidence clears the policy gates. It prefers updating an existing skill,
requires regression evidence for behavior changes, and may prepare a draft PR.
It never auto-merges, publishes, changes auth/permissions, edits installed plugin
caches, or treats its own maintenance tasks as product evidence.

Coverage is the recent local task history returned by the Windows Codex app. It
does not claim access to unrelated ChatGPT web chats, another computer/profile,
or deleted history.

The current companion runtime supports Revit 2024 on Windows 11 only. Revit 2025/2026 need
separate .NET 8 add-in builds and are intentionally blocked upstream.
