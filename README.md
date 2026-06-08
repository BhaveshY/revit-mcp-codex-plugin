# Revit MCP Codex Plugin

Codex plugin for Autodesk Revit 2024 workflows on Windows through the `mcp-server-for-revit` bridge.

## Install in Codex

```text
/plugin marketplace add BhaveshY/revit-mcp-codex-plugin
/plugin install revit-mcp-cowork@revit-mcp-codex-plugin
/reload-plugins
```

## Required local setup

The marketplace install only installs the Codex-side plugin. Revit also needs the local addin and Node runtime:

- Autodesk Revit 2024 on Windows.
- Node.js 18+ available on PATH so Codex can launch `npx -y mcp-server-for-revit`.
- The RevitMCP addin copied under `%AppData%\Autodesk\Revit\Addins4\`.
- Revit open with a project document loaded and the RevitMCP bridge listening.

Use the `/revit-mcp-cowork:setup-revit` skill for step-by-step addin setup.

## First health check

Do **not** use the upstream `say_hello` tool; it opens a blocking Revit dialog. Use the setup skill's `send_code_to_revit` health check, then `get_current_view_info`.

## Safety notes

This plugin bundles Revit safety skills and hook scripts for clients that support hook execution. Core safety rules are still documented in the skills: avoid silent list caps, cite source tools for quantities, and verify destructive operations before applying changes.
