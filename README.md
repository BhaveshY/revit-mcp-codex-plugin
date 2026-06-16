# Revit MCP Codex Plugin

Codex Desktop plugin for Autodesk Revit 2024 workflows on Windows through the `mcp-server-for-revit` bridge.

## Quick Install For Codex Desktop

Run these commands in PowerShell:

```powershell
codex plugin marketplace add https://github.com/BhaveshY/revit-mcp-codex-plugin
codex plugin add revit-mcp-cowork@revit-mcp-codex-plugin
```

Then fully quit and reopen Codex Desktop. Existing Codex windows may not see newly installed plugins, MCP servers, or PATH changes until restart.

## Windows One-Time Setup

The Codex plugin is only the Codex side of the bridge. A Windows machine also needs:

- Autodesk Revit 2024.
- Node.js 22 LTS recommended. Node.js 20+ is supported, but Node 24 can require Visual Studio C++ Build Tools for the MCP server's native dependency.
- The npm bridge package: `npm install -g mcp-server-for-revit`.
- The Revit MCP addin installed under `%AppData%\Autodesk\Revit\Addins\2024\`.
- Revit open with a project document loaded and the Revit MCP bridge listening.

For a full setup on a fresh Windows PC, clone this repo and run:

```powershell
git clone https://github.com/BhaveshY/revit-mcp-codex-plugin.git
cd revit-mcp-codex-plugin
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-codex-desktop.ps1
```

The script installs user-local Node 22 if needed, installs `mcp-server-for-revit`, downloads the Revit 2024 addin release, and installs this Codex plugin from the GitHub repo source.

Detailed manual steps are in [WINDOWS_CODEX_DESKTOP_INSTALL.md](./WINDOWS_CODEX_DESKTOP_INSTALL.md).

## Codex Compatibility

This repository is a Codex plugin marketplace. A tested install registers:

- plugin: `revit-mcp-cowork`
- MCP server: `revit`
- transport: stdio
- command: `cmd /c .\scripts\launch-revit-mcp.cmd`

The launcher prefers a globally installed `mcp-server-for-revit.cmd`, then falls back to `npx.cmd`. It checks PATH, `%USERPROFILE%\.local\nodejs22`, `%USERPROFILE%\.local\nodejs`, and standard Program Files Node.js locations. The npm package `mcp-server-for-revit` is published as `1.0.0`.

Codex can install the plugin and register the MCP server from the repo link. Live Revit operations only work after Node, the npm bridge, and the Revit addin are installed on the user's Windows PC.

## First Health Check

After installing, open Revit 2024, open a project, start the Revit MCP listener, then ask Codex:

```text
Run a Revit health check.
```

Do not use the upstream `say_hello` tool; it opens a blocking Revit dialog. The setup skill uses a non-blocking `send_code_to_revit` health check, then `get_current_view_info`.

## Safety Notes

This plugin bundles Revit safety skills and hook scripts for Codex. Core safety rules are also documented in the skills: avoid silent list caps, cite source tools for quantities, and verify destructive operations before applying changes.
