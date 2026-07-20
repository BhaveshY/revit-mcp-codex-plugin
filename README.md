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

The current companion runtime supports Revit 2024 on Windows 11 only. Revit 2025/2026 need
separate .NET 8 add-in builds and are intentionally blocked upstream.
